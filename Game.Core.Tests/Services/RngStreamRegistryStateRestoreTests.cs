using System;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class RngStreamRegistryStateRestoreTests
{
    private static readonly string[] RequiredStreamNames =
    {
        RngStreamType.Run,
        RngStreamType.Combat,
        RngStreamType.Event,
        RngStreamType.Loot,
        RngStreamType.Shop,
        RngStreamType.Offer,
    };

    // ACC:T9.5
    [Fact]
    public void ShouldMatchUninterruptedSequence_WhenRestoringSerializedState()
    {
        const int seed = 20260404;
        const int warmupCount = 6;
        const int divergenceCount = 4;
        const int validationCount = 10;
        const int minInclusive = 0;
        const int maxExclusive = 1_000_000;
        foreach (var streamName in RequiredStreamNames)
        {
            var uninterruptedRegistry = CreateRegistry(seed);
            var restoredRegistry = CreateRegistry(seed);

            var uninterruptedPrefix = DrawSequence(uninterruptedRegistry, streamName, warmupCount, minInclusive, maxExclusive);
            var restoredPrefix = DrawSequence(restoredRegistry, streamName, warmupCount, minInclusive, maxExclusive);
            uninterruptedPrefix.Should().Equal(restoredPrefix);

            var snapshot = restoredRegistry.Snapshot(streamName);

            var expectedTail = DrawSequence(uninterruptedRegistry, streamName, validationCount, minInclusive, maxExclusive);

            _ = DrawSequence(restoredRegistry, streamName, divergenceCount, minInclusive, maxExclusive);
            var sequenceWithoutRestore = DrawSequence(restoredRegistry, streamName, validationCount, minInclusive, maxExclusive);

            sequenceWithoutRestore.Should().NotEqual(expectedTail,
                because: "without restoring, stream '{0}' must diverge after extra draws", streamName);

            restoredRegistry.Restore(streamName, snapshot);
            var actualTail = DrawSequence(restoredRegistry, streamName, validationCount, minInclusive, maxExclusive);

            actualTail.Should().Equal(expectedTail,
                because: "after restoring stream '{0}', sequence must match uninterrupted execution", streamName);

            restoredRegistry.GetPosition(streamName).Should().Be(warmupCount + validationCount,
                because: "after restore, stream '{0}' should return to uninterrupted step index", streamName);
        }
    }

    // ACC:T9.5
    [Fact]
    public void ShouldKeepOtherStreamUnchanged_WhenRestoringTargetStreamState()
    {
        const int seed = 20260404;
        const int prefixCount = 3;
        const int targetAdvanceCount = 9;
        const int validationCount = 12;
        const int minInclusive = 0;
        const int maxExclusive = 1_000_000;
        var targetStreamName = RngStreamType.Run;
        var untouchedStreamName = RngStreamType.Combat;

        var baselineRegistry = CreateRegistry(seed);
        var restoredRegistry = CreateRegistry(seed);

        var baselinePrefix = DrawSequence(baselineRegistry, untouchedStreamName, prefixCount, minInclusive, maxExclusive);
        var restoredPrefix = DrawSequence(restoredRegistry, untouchedStreamName, prefixCount, minInclusive, maxExclusive);
        baselinePrefix.Should().Equal(restoredPrefix);

        var snapshot = restoredRegistry.Snapshot(targetStreamName);
        var untouchedPositionBefore = restoredRegistry.GetPosition(untouchedStreamName);

        _ = DrawSequence(restoredRegistry, targetStreamName, targetAdvanceCount, minInclusive, maxExclusive);
        restoredRegistry.Restore(targetStreamName, snapshot);

        var untouchedPositionAfter = restoredRegistry.GetPosition(untouchedStreamName);
        untouchedPositionAfter.Should().Be(untouchedPositionBefore,
            because: "restoring one stream must not mutate step count of another stream");

        var expectedUntouchedTail = DrawSequence(baselineRegistry, untouchedStreamName, validationCount, minInclusive, maxExclusive);
        var actualUntouchedTail = DrawSequence(restoredRegistry, untouchedStreamName, validationCount, minInclusive, maxExclusive);

        actualUntouchedTail.Should().Equal(expectedUntouchedTail,
            because: "stream restoration must be isolated so other streams keep their deterministic sequence");
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
            because: "the RNG stream registry implementation must be constructible for state restore checks");

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
