using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0009AcceptanceTests
{
    private const int Seed = 20260404;

    private static readonly string[] RequiredStreamNames =
    {
        RngStreamType.Run,
        RngStreamType.Combat,
        RngStreamType.Event,
        RngStreamType.Loot,
        RngStreamType.Shop,
        RngStreamType.Offer,
    };


    // ACC:T9.1
    [Fact]
    public void ShouldProvideRequiredNamedStreams_WhenSamplingFromRegistry()
    {
        var registry = CreateRegistry(Seed);

        foreach (var streamName in RequiredStreamNames)
        {
            var sample = registry.NextInt(streamName, 0, 1_000_000);

            sample.Should().BeGreaterThanOrEqualTo(0);
            sample.Should().BeLessThan(1_000_000);
            registry.GetPosition(streamName).Should().Be(1L,
                because: "named deterministic streams must be registered and sampled through the registry");
        }
    }

    // ACC:T9.2
    [Fact]
    public void ShouldResumeSequenceFromSnapshot_WhenRestoringNamedStreamState()
    {
        const int warmupCount = 5;
        const int divergenceCount = 3;
        const int validationCount = 10;
        foreach (var streamName in RequiredStreamNames)
        {
            var baselineRegistry = CreateRegistry(Seed);
            var restoredRegistry = CreateRegistry(Seed);

            var baselinePrefix = DrawSequence(baselineRegistry, streamName, warmupCount, 0, 1_000_000);
            var restoredPrefix = DrawSequence(restoredRegistry, streamName, warmupCount, 0, 1_000_000);
            baselinePrefix.Should().Equal(restoredPrefix);

            var snapshot = restoredRegistry.Snapshot(streamName);

            var expectedTail = DrawSequence(baselineRegistry, streamName, validationCount, 0, 1_000_000);
            _ = DrawSequence(restoredRegistry, streamName, divergenceCount, 0, 1_000_000);
            restoredRegistry.Restore(streamName, snapshot);

            var restoredTail = DrawSequence(restoredRegistry, streamName, validationCount, 0, 1_000_000);
            restoredTail.Should().Equal(expectedTail,
                because: "restored stream '{0}' must continue with the same outputs as uninterrupted execution", streamName);
            restoredRegistry.GetPosition(streamName).Should().Be(warmupCount + validationCount,
                because: "restored stream '{0}' should return to baseline position continuity", streamName);
        }
    }

    // ACC:T9.2
    [Fact]
    public void ShouldSerializeSeedStateAndPosition_WhenCapturingSnapshot()
    {
        var registry = CreateRegistry(Seed);
        var expectedSeedToken = $"{unchecked((ulong)(long)Seed):X16}";

        foreach (var streamName in RequiredStreamNames)
        {
            _ = registry.NextInt(streamName, 0, 100);
            var snapshot = registry.Snapshot(streamName);
            var parts = snapshot.Split('|');

            parts.Should().HaveCount(4);
            parts[0].Should().Be(streamName);
            parts[1].Should().Be(expectedSeedToken);
            parts[2].Should().MatchRegex("^[0-9A-F]{16}$");
            parts[3].Should().Be("1");
        }
    }

    // ACC:T9.6
    [Fact]
    public void ShouldRejectUnknownStreamSampling_WhenStreamNameIsNotRegistered()
    {
        var registry = CreateRegistry(Seed);
        var positionsBefore = CapturePositions(registry);
        var snapshotsBefore = CaptureSnapshots(registry);

        Action sampleUnknownStream = () => registry.NextInt("unknown.stream", 0, 10);

        var failure = sampleUnknownStream.Should().Throw<ArgumentException>(
            because: "deterministic systems must sample only from registered named streams");
        failure.Which.ParamName.Should().Be("streamName");
        CapturePositions(registry).Should().BeEquivalentTo(positionsBefore,
            because: "failed unknown-stream sampling must not advance any registered stream position");
        CaptureSnapshots(registry).Should().BeEquivalentTo(snapshotsBefore,
            because: "failed unknown-stream sampling must not mutate registered stream state");
    }

    private static IReadOnlyDictionary<string, long> CapturePositions(IRngStreamRegistry registry)
    {
        var result = new Dictionary<string, long>(StringComparer.Ordinal);
        foreach (var streamName in RequiredStreamNames)
        {
            result[streamName] = registry.GetPosition(streamName);
        }

        return result;
    }

    private static IReadOnlyDictionary<string, string> CaptureSnapshots(IRngStreamRegistry registry)
    {
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var streamName in RequiredStreamNames)
        {
            result[streamName] = registry.Snapshot(streamName);
        }

        return result;
    }

    private static int[] DrawSequence(
        IRngStreamRegistry registry,
        string streamName,
        int sampleCount,
        int minInclusive,
        int maxExclusive)
    {
        var values = new int[sampleCount];
        for (var index = 0; index < sampleCount; index++)
        {
            values[index] = registry.NextInt(streamName, minInclusive, maxExclusive);
        }

        return values;
    }

    private static IRngStreamRegistry CreateRegistry(int seed)
    {
        var implementationCandidates = typeof(IRngStreamRegistry).Assembly
            .GetTypes()
            .Where(type => typeof(IRngStreamRegistry).IsAssignableFrom(type))
            .Where(type => type is { IsAbstract: false, IsInterface: false })
            .ToArray();

        implementationCandidates.Should().ContainSingle(
            because: "Task 9 requires one concrete IRngStreamRegistry implementation");

        var registry = TryCreateInstance(implementationCandidates[0], seed);

        registry.Should().NotBeNull(
            because: "the RNG stream registry implementation must be constructible for acceptance checks");

        return registry!;
    }

    private static IRngStreamRegistry? TryCreateInstance(Type implementationType, int seed)
    {
        var constructors = implementationType
            .GetConstructors()
            .OrderBy(constructor => constructor.GetParameters().Length)
            .ToArray();

        foreach (var constructor in constructors)
        {
            var parameters = constructor.GetParameters();
            var arguments = new object?[parameters.Length];
            var canResolveAll = true;

            for (var index = 0; index < parameters.Length; index++)
            {
                if (!TryResolveConstructorArgument(parameters[index], seed, out var argument))
                {
                    canResolveAll = false;
                    break;
                }

                arguments[index] = argument;
            }

            if (!canResolveAll)
            {
                continue;
            }

            var instance = constructor.Invoke(arguments);
            if (instance is IRngStreamRegistry typedInstance)
            {
                return typedInstance;
            }
        }

        return null;
    }

    private static bool TryResolveConstructorArgument(ParameterInfo parameter, int seed, out object? argument)
    {
        if (parameter.HasDefaultValue)
        {
            argument = parameter.DefaultValue;
            return true;
        }

        if (parameter.ParameterType == typeof(int))
        {
            argument = IsSeedLikeParameter(parameter.Name) ? seed : 0;
            return true;
        }

        if (parameter.ParameterType == typeof(long))
        {
            argument = IsSeedLikeParameter(parameter.Name) ? (long)seed : 0L;
            return true;
        }

        if (parameter.ParameterType == typeof(string))
        {
            argument = string.Empty;
            return true;
        }

        if (parameter.ParameterType == typeof(bool))
        {
            argument = false;
            return true;
        }

        if (parameter.ParameterType.IsEnum)
        {
            argument = Enum.GetValues(parameter.ParameterType).GetValue(0);
            return true;
        }

        if (parameter.ParameterType.IsValueType)
        {
            argument = Activator.CreateInstance(parameter.ParameterType);
            return true;
        }

        argument = null;
        return false;
    }

    private static bool IsSeedLikeParameter(string? parameterName)
    {
        return parameterName is not null
            && parameterName.IndexOf("seed", StringComparison.OrdinalIgnoreCase) >= 0;
    }

}
