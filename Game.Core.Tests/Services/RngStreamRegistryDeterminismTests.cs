using System;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class RngStreamRegistryDeterminismTests
{
    // ACC:T9.3
    [Fact]
    public void ShouldProduceIdenticalOutputSequence_WhenUsingSameSeedForSameNamedStream()
    {
        const int seed = 20260404;
        const int sampleCount = 12;
        const int minInclusive = 0;
        const int maxExclusive = 1_000_000;
        var streamName = RngStreamType.Run;

        var leftRegistry = CreateRegistry(seed);
        var rightRegistry = CreateRegistry(seed);

        var leftSequence = DrawSequence(leftRegistry, streamName, sampleCount, minInclusive, maxExclusive);
        var rightSequence = DrawSequence(rightRegistry, streamName, sampleCount, minInclusive, maxExclusive);

        leftSequence.Should().Equal(rightSequence,
            because: "same initial seed and same named stream at the same step count must produce identical outputs");
        leftRegistry.GetPosition(streamName).Should().Be(sampleCount);
        rightRegistry.GetPosition(streamName).Should().Be(sampleCount);
    }

    // ACC:T9.3
    [Fact]
    public void ShouldKeepOtherStreamUnchanged_WhenDifferentNamedStreamAdvances()
    {
        const int seed = 20260404;
        const int warmupCount = 1;
        const int validationCount = 10;
        const int minInclusive = 0;
        const int maxExclusive = 1_000_000;
        var untouchedStreamName = RngStreamType.Combat;
        var advancedStreamName = RngStreamType.Event;

        var controlRegistry = CreateRegistry(seed);
        var mutatedRegistry = CreateRegistry(seed);

        var controlWarmup = DrawSequence(controlRegistry, untouchedStreamName, warmupCount, minInclusive, maxExclusive);
        var mutatedWarmup = DrawSequence(mutatedRegistry, untouchedStreamName, warmupCount, minInclusive, maxExclusive);

        controlWarmup.Should().Equal(mutatedWarmup);

        var positionBefore = mutatedRegistry.GetPosition(untouchedStreamName);
        _ = DrawSequence(mutatedRegistry, advancedStreamName, validationCount, minInclusive, maxExclusive);
        var positionAfter = mutatedRegistry.GetPosition(untouchedStreamName);

        positionAfter.Should().Be(positionBefore,
            because: "advancing one named stream must not change the state or step counter of other streams");

        var expectedTail = DrawSequence(controlRegistry, untouchedStreamName, validationCount, minInclusive, maxExclusive);
        var actualTail = DrawSequence(mutatedRegistry, untouchedStreamName, validationCount, minInclusive, maxExclusive);

        actualTail.Should().Equal(expectedTail,
            because: "stream isolation requires unaffected streams to keep the same future outputs");
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
            because: "the RNG stream registry implementation must be constructible for determinism checks");

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
