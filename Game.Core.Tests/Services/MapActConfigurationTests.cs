using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Config;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class MapActConfigurationTests
{
    private static ActConfig BuildActConfig(int actId)
    {
        var nodeGraph = JsonDocument.Parse("{\"start\":\"N-" + actId + "-1\"}").RootElement.Clone();
        var pools = JsonDocument.Parse("{\"normal\":[\"enemy_a\"]}").RootElement.Clone();
        var encounters = JsonDocument.Parse("[{\"id\":\"enc-" + actId + "\",\"type\":\"combat\"}]").RootElement.Clone();
        return new ActConfig("1.0", actId, nodeGraph, pools, encounters);
    }

    [Fact]
    public void ShouldReturnFalse_WhenRequestedActCountIsNonPositive()
    {
        var service = new MapActConfigurationService();
        var provider = new PropertyCountProvider(2);

        service.TryRunConfiguredActs(0, provider).Should().BeFalse();
        service.TryRunConfiguredActs(-1, provider).Should().BeFalse();
        provider.RequestedActIds.Should().BeEmpty();
    }

    [Fact]
    public void ShouldReturnFalse_WhenProviderIsNull()
    {
        var service = new MapActConfigurationService();

        service.TryRunConfiguredActs(1, null!).Should().BeFalse();
    }

    [Fact]
    public void ShouldReturnFalse_WhenProviderThrowsArgumentException()
    {
        var service = new MapActConfigurationService();
        var provider = new ThrowingProvider(
            configuredActCount: 2,
            actId => throw new ArgumentException($"Bad act {actId}", nameof(actId)));

        service.TryRunConfiguredActs(1, provider).Should().BeFalse();
    }

    [Fact]
    public void ShouldReturnFalse_WhenProviderThrowsInvalidOperationException()
    {
        var service = new MapActConfigurationService();
        var provider = new ThrowingProvider(
            configuredActCount: 2,
            _ => throw new InvalidOperationException("broken state"));

        service.TryRunConfiguredActs(1, provider).Should().BeFalse();
    }

    [Fact]
    public void ShouldResolveConfiguredCountFromCountLikeProperty()
    {
        var service = new MapActConfigurationService();
        var provider = new PropertyCountProvider(3);

        var success = service.TryRunConfiguredActs(3, provider);

        success.Should().BeTrue();
        provider.RequestedActIds.Should().Equal(1, 2, 3);
    }

    [Fact]
    public void ShouldResolveConfiguredCountFromCountLikeField()
    {
        var service = new MapActConfigurationService();
        var provider = new FieldCountProvider(2);

        var success = service.TryRunConfiguredActs(2, provider);

        success.Should().BeTrue();
        provider.RequestedActIds.Should().Equal(1, 2);
    }

    [Fact]
    public void ShouldResolveConfiguredCountFromCollectionProperty()
    {
        var service = new MapActConfigurationService();
        var provider = new CollectionPropertyProvider(2);

        var success = service.TryRunConfiguredActs(2, provider);

        success.Should().BeTrue();
        provider.RequestedActIds.Should().Equal(1, 2);
    }

    [Fact]
    public void ShouldResolveConfiguredCountFromCollectionField()
    {
        var service = new MapActConfigurationService();
        var provider = new CollectionFieldProvider(2);

        var success = service.TryRunConfiguredActs(2, provider);

        success.Should().BeTrue();
        provider.RequestedActIds.Should().Equal(1, 2);
    }

    [Fact]
    public void ShouldFallBackToLookupPath_WhenNoCountLikeMembersExist()
    {
        var service = new MapActConfigurationService();
        var provider = new NoCountMembersProvider(1);

        var success = service.TryRunConfiguredActs(1, provider);

        success.Should().BeTrue();
        provider.RequestedActIds.Should().Equal(1);
    }

    // ACC:T17.8
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(4)]
    public void ShouldRunConfiguredActCount_WhenActConfigurationIsSufficient(int configuredActCount)
    {
        var binding = MapActServiceBinding.TryCreate(out var diagnostics);
        binding.Should().NotBeNull(diagnostics);
        if (binding is null)
        {
            return;
        }

        var provider = new InMemoryActConfigProvider(configuredActCount);

        var result = binding.TryRunConfiguredActs(provider, configuredActCount);

        result.Success.Should().BeTrue(
            $"Expected run to succeed when requested count equals configured count ({configuredActCount}). {result.Diagnostics}");
        provider.RequestedActIds.Should().Equal(
            Enumerable.Range(1, configuredActCount),
            "runner should resolve acts exactly by configured count in deterministic order.");

        if (configuredActCount != 3)
        {
            provider.RequestedActIds.Count.Should().NotBe(3, "runner must not hardcode three acts.");
        }
    }

    // ACC:T17.8
    [Theory]
    [InlineData(1, 2)]
    [InlineData(2, 3)]
    [InlineData(4, 5)]
    public void ShouldFailWithoutPartialExecution_WhenConfiguredActsAreInsufficient(int configuredActCount, int requestedActCount)
    {
        var binding = MapActServiceBinding.TryCreate(out var diagnostics);
        binding.Should().NotBeNull(diagnostics);
        if (binding is null)
        {
            return;
        }

        var provider = new InMemoryActConfigProvider(configuredActCount);

        var result = binding.TryRunConfiguredActs(provider, requestedActCount);

        result.Success.Should().BeFalse(
            $"Expected failure when requested count ({requestedActCount}) exceeds configured count ({configuredActCount}). {result.Diagnostics}");
        provider.RequestedActIds.Should().BeEmpty("failed execution should keep progression unchanged and avoid partial consumption.");
    }

    private sealed class InMemoryActConfigProvider : IActConfigProvider
    {
        private readonly Dictionary<int, ActConfig> configs;
        private readonly List<int> requestedActIds;

        public InMemoryActConfigProvider(int configuredActCount)
        {
            if (configuredActCount <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(configuredActCount));
            }

            configs = Enumerable.Range(1, configuredActCount)
                .ToDictionary(actId => actId, BuildActConfig);
            requestedActIds = new List<int>();
        }

        public IReadOnlyList<int> RequestedActIds => requestedActIds;

        public ActConfig GetByActId(int actId)
        {
            requestedActIds.Add(actId);
            if (!configs.TryGetValue(actId, out var config))
            {
                throw new KeyNotFoundException($"Act config not found for act_id={actId}.");
            }

            return config;
        }

    }

    private sealed class ThrowingProvider : IActConfigProvider
    {
        private readonly Func<int, ActConfig> behavior;

        public ThrowingProvider(int configuredActCount, Func<int, ActConfig> behavior)
        {
            this.behavior = behavior;
            ActConfigCount = configuredActCount;
        }

        public int ActConfigCount { get; }

        public ActConfig GetByActId(int actId)
        {
            return behavior(actId);
        }
    }

    private sealed class PropertyCountProvider : IActConfigProvider
    {
        private readonly Dictionary<int, ActConfig> configs;
        private readonly List<int> requestedActIds = new();

        public PropertyCountProvider(int configuredActCount)
        {
            configs = Enumerable.Range(1, configuredActCount)
                .ToDictionary(id => id, BuildActConfig);
        }

        public int ActConfigCount => configs.Count;
        public IReadOnlyList<int> RequestedActIds => requestedActIds;

        public ActConfig GetByActId(int actId)
        {
            requestedActIds.Add(actId);
            return configs[actId];
        }
    }

    private sealed class FieldCountProvider : IActConfigProvider
    {
        private readonly Dictionary<int, ActConfig> configs;
        private readonly List<int> requestedActIds = new();

        public FieldCountProvider(int configuredActCount)
        {
            configs = Enumerable.Range(1, configuredActCount)
                .ToDictionary(id => id, BuildActConfig);
            actConfigCount = configuredActCount;
        }

        public int actConfigCount;
        public IReadOnlyList<int> RequestedActIds => requestedActIds;

        public ActConfig GetByActId(int actId)
        {
            requestedActIds.Add(actId);
            return configs[actId];
        }
    }

    private sealed class CollectionPropertyProvider : IActConfigProvider
    {
        private readonly Dictionary<int, ActConfig> configs;
        private readonly List<int> requestedActIds = new();

        public CollectionPropertyProvider(int configuredActCount)
        {
            configs = Enumerable.Range(1, configuredActCount)
                .ToDictionary(id => id, BuildActConfig);
            ActConfigs = Enumerable.Range(1, configuredActCount).Select(BuildActConfig).ToList();
        }

        public int ActConfigCount => 0;
        public List<ActConfig> ActConfigs { get; }
        public IReadOnlyList<int> RequestedActIds => requestedActIds;

        public ActConfig GetByActId(int actId)
        {
            requestedActIds.Add(actId);
            return configs[actId];
        }
    }

    private sealed class CollectionFieldProvider : IActConfigProvider
    {
        private readonly Dictionary<int, ActConfig> configs;
        private readonly List<int> requestedActIds = new();

        public CollectionFieldProvider(int configuredActCount)
        {
            configs = Enumerable.Range(1, configuredActCount)
                .ToDictionary(id => id, BuildActConfig);
            actConfigCount = 0;
            actConfigs = Enumerable.Range(1, configuredActCount).Select(BuildActConfig).ToList();
        }

        public int actConfigCount;
        public List<ActConfig> actConfigs;
        public IReadOnlyList<int> RequestedActIds => requestedActIds;

        public ActConfig GetByActId(int actId)
        {
            requestedActIds.Add(actId);
            return configs[actId];
        }
    }

    private sealed class NoCountMembersProvider : IActConfigProvider
    {
        private readonly Dictionary<int, ActConfig> configs;
        private readonly List<int> requestedActIds = new();

        public NoCountMembersProvider(int configuredActCount)
        {
            configs = Enumerable.Range(1, configuredActCount)
                .ToDictionary(id => id, BuildActConfig);
            Items = new List<ActConfig>();
        }

        public List<ActConfig> Items { get; }
        public IReadOnlyList<int> RequestedActIds => requestedActIds;

        public ActConfig GetByActId(int actId)
        {
            requestedActIds.Add(actId);
            return configs[actId];
        }
    }

    private sealed class MapActServiceBinding
    {
        private static readonly string[] CandidateTypeNames =
        {
            "Game.Core.Services.MapActConfigurationService",
            "Game.Core.Services.MapActRunnerService",
            "Game.Core.Services.MapActRunner",
            "Game.Core.Services.MapRunService",
            "Game.Core.Engine.MapActRunner"
        };

        private static readonly string[] CandidateMethodNames =
        {
            "TryRunConfiguredActs",
            "TryRunActs",
            "TryExecuteConfiguredActs",
            "TryExecuteActs",
            "TryRunMapActs"
        };

        private readonly Type serviceType;
        private readonly MethodInfo runMethod;

        private MapActServiceBinding(Type serviceType, MethodInfo runMethod)
        {
            this.serviceType = serviceType;
            this.runMethod = runMethod;
        }

        public static MapActServiceBinding? TryCreate(out string diagnostics)
        {
            var coreAssembly = typeof(IActConfigProvider).Assembly;

            foreach (var typeName in CandidateTypeNames)
            {
                var candidateType = coreAssembly.GetType(typeName, throwOnError: false, ignoreCase: false);
                if (candidateType is null)
                {
                    continue;
                }

                var candidateMethod = candidateType
                    .GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                    .FirstOrDefault(method =>
                        CandidateMethodNames.Contains(method.Name, StringComparer.Ordinal) &&
                        IsSupportedRunSignature(method));

                if (candidateMethod is null)
                {
                    continue;
                }

                diagnostics = $"Bound map act runner: {candidateType.FullName}.{candidateMethod.Name}.";
                return new MapActServiceBinding(candidateType, candidateMethod);
            }

            diagnostics =
                "Map act runner binding not found. Expected a public bool-returning runner method that accepts requested act count and optional IActConfigProvider.";
            return null;
        }

        public InvocationResult TryRunConfiguredActs(InMemoryActConfigProvider provider, int requestedActCount)
        {
            if (!TryCreateInstance(provider, out var instance, out var instanceDiagnostics))
            {
                return new InvocationResult(false, instanceDiagnostics);
            }

            if (!TryBuildArguments(provider, requestedActCount, out var args, out var argsDiagnostics))
            {
                return new InvocationResult(false, argsDiagnostics);
            }

            try
            {
                var returnValue = runMethod.Invoke(instance, args);
                if (returnValue is bool success)
                {
                    return new InvocationResult(success, $"Invoked {serviceType.FullName}.{runMethod.Name}.");
                }

                return new InvocationResult(
                    false,
                    $"Runner returned non-bool result ({returnValue?.GetType().FullName ?? "null"}); expected bool success signal.");
            }
            catch (TargetInvocationException ex) when (ex.InnerException is KeyNotFoundException or InvalidOperationException or ArgumentException)
            {
                return new InvocationResult(false, $"Runner invocation failed: {ex.InnerException!.GetType().Name}: {ex.InnerException.Message}");
            }
        }

        private static bool IsSupportedRunSignature(MethodInfo method)
        {
            if (method.ReturnType != typeof(bool))
            {
                return false;
            }

            var hasRequestedCount = false;
            foreach (var parameter in method.GetParameters())
            {
                if (parameter.ParameterType == typeof(int))
                {
                    hasRequestedCount = true;
                    continue;
                }

                if (typeof(IActConfigProvider).IsAssignableFrom(parameter.ParameterType))
                {
                    continue;
                }

                return false;
            }

            return hasRequestedCount;
        }

        private bool TryCreateInstance(InMemoryActConfigProvider provider, out object? instance, out string diagnostics)
        {
            instance = null;
            diagnostics = string.Empty;

            if (runMethod.IsStatic)
            {
                diagnostics = "Runner method is static.";
                return true;
            }

            var parameterlessConstructor = serviceType.GetConstructor(Type.EmptyTypes);
            if (parameterlessConstructor is not null)
            {
                instance = parameterlessConstructor.Invoke(Array.Empty<object>());
                diagnostics = "Runner created via parameterless constructor.";
                return true;
            }

            var providerConstructor = serviceType.GetConstructor(new[] { typeof(IActConfigProvider) });
            if (providerConstructor is not null)
            {
                instance = providerConstructor.Invoke(new object[] { provider });
                diagnostics = "Runner created via IActConfigProvider constructor.";
                return true;
            }

            diagnostics = $"Cannot construct {serviceType.FullName}: expected parameterless or IActConfigProvider constructor.";
            return false;
        }

        private bool TryBuildArguments(
            InMemoryActConfigProvider provider,
            int requestedActCount,
            out object?[] args,
            out string diagnostics)
        {
            var parameters = runMethod.GetParameters();
            args = new object?[parameters.Length];

            for (var index = 0; index < parameters.Length; index++)
            {
                var parameterType = parameters[index].ParameterType;
                if (parameterType == typeof(int))
                {
                    args[index] = requestedActCount;
                    continue;
                }

                if (typeof(IActConfigProvider).IsAssignableFrom(parameterType))
                {
                    args[index] = provider;
                    continue;
                }

                diagnostics = $"Unsupported runner parameter type: {parameterType.FullName}.";
                return false;
            }

            diagnostics = "Runner arguments built successfully.";
            return true;
        }
    }

    private sealed record InvocationResult(bool Success, string Diagnostics);
}
