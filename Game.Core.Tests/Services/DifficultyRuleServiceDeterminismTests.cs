using System;
using System.Collections;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Config;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class DifficultyRuleServiceDeterminismTests
{
    private static readonly string[] ResolveMethodCandidates =
    {
        "ResolveModifiers",
        "ResolveDifficultyModifiers",
        "ResolveRules",
        "ResolveRuleModifiers",
        "GetModifiers",
        "GetRuleModifiers",
        "GetDifficultyModifiers",
    };

    // ACC:T27.4
    [Fact]
    [Trait("acceptance", "ACC:T27.4")]
    public async Task ShouldReturnEquivalentComparableOutput_WhenInvokedRepeatedlyWithSameDifficulty()
    {
        const int difficultyId = 10;

        var firstResult = await InvokeResolveModifiersAsync(difficultyId);
        var secondResult = await InvokeResolveModifiersAsync(difficultyId);

        var firstSignature = BuildDeterministicSignature(firstResult);
        var secondSignature = BuildDeterministicSignature(secondResult);

        firstResult.Should().NotBeNull("resolver output should be comparable for determinism verification");
        secondResult.Should().NotBeNull("resolver output should be comparable for determinism verification");
        secondSignature.Should().Be(firstSignature,
            because: "the same input difficulty must produce value-equal output across repeated calls");
        secondResult.Should().BeEquivalentTo(firstResult,
            because: "determinism requires equivalent value structure, not runtime ordering drift");
    }

    // ACC:T27.4
    [Fact]
    [Trait("acceptance", "ACC:T27.4")]
    public async Task ShouldKeepOutputUnchanged_WhenExternalRunDifficultyStateMutatesBetweenInvocations()
    {
        const int inputDifficultyId = 10;
        var originalDifficultyId = RunDifficultyState.GetConfirmedDifficulty();

        try
        {
            RunDifficultyState.SetConfirmedDifficulty(1);
            var baselineResult = await InvokeResolveModifiersAsync(inputDifficultyId);
            var baselineSignature = BuildDeterministicSignature(baselineResult);

            RunDifficultyState.SetConfirmedDifficulty(9);
            var mutatedStateResult = await InvokeResolveModifiersAsync(inputDifficultyId);
            var mutatedStateSignature = BuildDeterministicSignature(mutatedStateResult);

            mutatedStateSignature.Should().Be(baselineSignature,
                because: "resolver output must not depend on mutable global state when difficulty input is explicit");
            mutatedStateResult.Should().BeEquivalentTo(baselineResult,
                because: "deterministic mapping must remain input-driven and unchanged by ambient state");
        }
        finally
        {
            RunDifficultyState.SetConfirmedDifficulty(originalDifficultyId);
        }
    }

    // ACC:T27.6
    [Theory]
    [InlineData(1)]
    [InlineData(5)]
    [InlineData(10)]
    [Trait("acceptance", "ACC:T27.6")]
    public async Task ShouldProduceDeterministicResultsAcrossDifficultySamples_WhenExecutedRepeatedly(int difficultyId)
    {
        var firstResult = await InvokeResolveModifiersAsync(difficultyId);
        var secondResult = await InvokeResolveModifiersAsync(difficultyId);

        BuildDeterministicSignature(secondResult).Should().Be(BuildDeterministicSignature(firstResult),
            because: "local re-runs must produce consistent conclusions for each sampled difficulty");
    }

    // ACC:T27.6
    [Fact]
    [Trait("acceptance", "ACC:T27.6")]
    public async Task ShouldReturnDifferentRuleSets_WhenDifficultyCrossesOverplayThreshold()
    {
        var belowThresholdResult = await InvokeResolveModifiersAsync(9);
        var thresholdResult = await InvokeResolveModifiersAsync(10);

        var belowThresholdSignature = BuildDeterministicSignature(belowThresholdResult);
        var thresholdSignature = BuildDeterministicSignature(thresholdResult);

        thresholdSignature.Should().NotBe(belowThresholdSignature,
            because: "difficulty mapping rules must change when crossing the overplay threshold boundary");
    }

    private static async Task<object?> InvokeResolveModifiersAsync(int difficultyId)
    {
        var serviceType = ResolveDifficultyRuleServiceType();
        var method = ResolveResolverMethod(serviceType, difficultyId, out var invocationArguments);

        object? serviceInstance = null;
        if (!method.IsStatic)
        {
            serviceInstance = CreateServiceInstance(serviceType);
        }

        var invocationResult = method.Invoke(serviceInstance, invocationArguments);
        if (invocationResult is Task task)
        {
            await task.ConfigureAwait(false);
            var resultProperty = task.GetType().GetProperty("Result", BindingFlags.Public | BindingFlags.Instance);
            return resultProperty?.GetValue(task);
        }

        return invocationResult;
    }

    private static Type ResolveDifficultyRuleServiceType()
    {
        var assembly = typeof(DifficultyConfig).Assembly;
        var candidates = assembly
            .GetTypes()
            .Where(type => type.IsClass && !type.IsAbstract)
            .Where(type => type.Name.Equals("DifficultyRuleService", StringComparison.Ordinal))
            .ToArray();

        candidates.Should().ContainSingle(
            because: "Task 27 requires one concrete DifficultyRuleService implementation in Game.Core.Services");

        return candidates[0];
    }

    private static MethodInfo ResolveResolverMethod(Type serviceType, int difficultyId, out object?[] invocationArguments)
    {
        var methods = serviceType
            .GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
            .Where(method => ResolveMethodCandidates.Contains(method.Name, StringComparer.OrdinalIgnoreCase))
            .OrderBy(method => method.GetParameters().Length)
            .ToArray();

        methods.Should().NotBeEmpty(
            because: "DifficultyRuleService must expose a public resolver method for difficulty-to-modifiers mapping");

        foreach (var method in methods)
        {
            if (TryBuildInvocationArguments(method.GetParameters(), difficultyId, out invocationArguments))
            {
                return method;
            }
        }

        throw new InvalidOperationException(
            "No resolver method accepted a difficulty-driven argument set. Expected int difficultyId or DifficultyConfig-based input.");
    }

    private static object CreateServiceInstance(Type serviceType)
    {
        var constructors = serviceType
            .GetConstructors()
            .OrderBy(constructor => constructor.GetParameters().Length)
            .ToArray();

        constructors.Should().NotBeEmpty(
            because: "DifficultyRuleService must be constructible to execute deterministic mapping checks");

        foreach (var constructor in constructors)
        {
            if (!TryBuildConstructorArguments(constructor.GetParameters(), out var arguments))
            {
                continue;
            }

            try
            {
                var instance = constructor.Invoke(arguments);
                if (instance is not null)
                {
                    return instance;
                }
            }
            catch
            {
            }
        }

        throw new InvalidOperationException("Failed to construct DifficultyRuleService with resolvable constructor arguments.");
    }

    private static bool TryBuildInvocationArguments(ParameterInfo[] parameters, int difficultyId, out object?[] arguments)
    {
        arguments = new object?[parameters.Length];
        var hasDifficultyInput = false;

        for (var index = 0; index < parameters.Length; index++)
        {
            if (!TryResolveArgument(parameters[index], difficultyId, out var argument, out var resolvedFromDifficulty))
            {
                return false;
            }

            arguments[index] = argument;
            hasDifficultyInput = hasDifficultyInput || resolvedFromDifficulty;
        }

        return hasDifficultyInput;
    }

    private static bool TryBuildConstructorArguments(ParameterInfo[] parameters, out object?[] arguments)
    {
        arguments = new object?[parameters.Length];

        for (var index = 0; index < parameters.Length; index++)
        {
            var parameter = parameters[index];

            if (parameter.HasDefaultValue)
            {
                arguments[index] = parameter.DefaultValue;
                continue;
            }

            var parameterType = parameter.ParameterType;
            if (parameterType == typeof(string))
            {
                arguments[index] = string.Empty;
                continue;
            }

            if (parameterType == typeof(int))
            {
                arguments[index] = 0;
                continue;
            }

            if (parameterType == typeof(long))
            {
                arguments[index] = 0L;
                continue;
            }

            if (parameterType == typeof(bool))
            {
                arguments[index] = false;
                continue;
            }

            if (parameterType.IsEnum)
            {
                arguments[index] = Enum.GetValues(parameterType).GetValue(0);
                continue;
            }

            if (parameterType.IsValueType)
            {
                arguments[index] = Activator.CreateInstance(parameterType);
                continue;
            }

            arguments[index] = null;
        }

        return true;
    }

    private static bool TryResolveArgument(
        ParameterInfo parameter,
        int difficultyId,
        out object? argument,
        out bool resolvedFromDifficulty)
    {
        resolvedFromDifficulty = false;

        if (parameter.HasDefaultValue)
        {
            argument = parameter.DefaultValue;
            return true;
        }

        var parameterType = parameter.ParameterType;
        var parameterName = parameter.Name ?? string.Empty;

        if (parameterType == typeof(int))
        {
            if (IsDifficultyLikeParameter(parameterName))
            {
                argument = difficultyId;
                resolvedFromDifficulty = true;
            }
            else
            {
                argument = 0;
            }

            return true;
        }

        if (parameterType == typeof(int?))
        {
            if (IsDifficultyLikeParameter(parameterName))
            {
                argument = difficultyId;
                resolvedFromDifficulty = true;
            }
            else
            {
                argument = null;
            }

            return true;
        }

        if (parameterType == typeof(DifficultyConfig))
        {
            argument = CreateDifficultyConfigSnapshot(difficultyId);
            resolvedFromDifficulty = true;
            return true;
        }

        if (parameterType == typeof(string))
        {
            argument = string.Empty;
            return true;
        }

        if (parameterType == typeof(bool))
        {
            argument = false;
            return true;
        }

        if (parameterType == typeof(long))
        {
            argument = 0L;
            return true;
        }

        if (parameterType.IsEnum)
        {
            argument = Enum.GetValues(parameterType).GetValue(0);
            return true;
        }

        if (parameterType.IsValueType)
        {
            argument = Activator.CreateInstance(parameterType);
            return true;
        }

        argument = null;
        return false;
    }

    private static DifficultyConfig CreateDifficultyConfigSnapshot(int difficultyId)
    {
        return new DifficultyConfig(
            DifficultyId: difficultyId,
            LabelKey: $"difficulty.label.{difficultyId}",
            DescriptionKey: $"difficulty.description.{difficultyId}",
            RulesetId: $"ruleset.{difficultyId}");
    }

    private static bool IsDifficultyLikeParameter(string parameterName)
    {
        return parameterName.IndexOf("difficulty", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    private static string BuildDeterministicSignature(object? value)
    {
        return BuildDeterministicSignature(value, depth: 0);
    }

    private static string BuildDeterministicSignature(object? value, int depth)
    {
        if (depth > 12)
        {
            return "<depth-limit>";
        }

        if (value is null)
        {
            return "null";
        }

        if (value is string text)
        {
            return $"\"{text}\"";
        }

        if (value is DateTime dateTime)
        {
            return dateTime.ToString("O", CultureInfo.InvariantCulture);
        }

        if (value is DateTimeOffset dateTimeOffset)
        {
            return dateTimeOffset.ToString("O", CultureInfo.InvariantCulture);
        }

        var valueType = value.GetType();
        if (valueType.IsEnum || valueType.IsPrimitive || value is decimal || value is Guid)
        {
            return Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty;
        }

        if (value is IDictionary dictionary)
        {
            var tokens = dictionary.Keys
                .Cast<object?>()
                .Select(key => new
                {
                    KeyToken = BuildDeterministicSignature(key, depth + 1),
                    ValueToken = BuildDeterministicSignature(dictionary[key], depth + 1),
                })
                .OrderBy(token => token.KeyToken, StringComparer.Ordinal)
                .Select(token => $"{token.KeyToken}:{token.ValueToken}");

            return "{" + string.Join(",", tokens) + "}";
        }

        if (value is IEnumerable enumerable)
        {
            var tokens = enumerable
                .Cast<object?>()
                .Select(item => BuildDeterministicSignature(item, depth + 1));

            return "[" + string.Join(",", tokens) + "]";
        }

        var properties = valueType
            .GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(property => property.CanRead && property.GetIndexParameters().Length == 0)
            .OrderBy(property => property.Name, StringComparer.Ordinal)
            .ToArray();

        if (properties.Length == 0)
        {
            return value.ToString() ?? (valueType.FullName ?? "<unknown>");
        }

        var propertyTokens = properties
            .Select(property => $"{property.Name}:{BuildDeterministicSignature(property.GetValue(value), depth + 1)}");

        return "{" + string.Join(",", propertyTokens) + "}";
    }
}
