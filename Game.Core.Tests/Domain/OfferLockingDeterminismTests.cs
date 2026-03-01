using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Offers;
using Xunit;

namespace Game.Core.Tests.Domain;

public sealed class OfferLockingDeterminismTests
{
    // ACC:T4.7
    [Fact]
    public void Should_KeepStableIdsUnchanged_When_OnlyDisplayOrderChanges()
    {
        var service = CreateOfferServiceForDeterminismTests();
        var provenance = CreateProvenance();
        var orderedCandidates = CreateCandidatesInDisplayOrder("offer.alpha", "offer.beta", "offer.gamma");
        var rotatedCandidates = new[] { orderedCandidates[2], orderedCandidates[0], orderedCandidates[1] };

        var orderedIds = orderedCandidates.Select(item => item.OfferItemId).ToArray();
        var rotatedIds = rotatedCandidates.Select(item => item.OfferItemId).ToArray();
        orderedIds.Should().NotEqual(rotatedIds,
            because: "this negative path changes only display order");

        var lockWithOriginalOrder = service.LockOffer("ctx-order-a", orderedCandidates, provenance);
        var lockWithRotatedOrder = service.LockOffer("ctx-order-b", rotatedCandidates, provenance);

        lockWithOriginalOrder.StableIds.Should().NotBeEmpty();
        lockWithOriginalOrder.StableIds.Should().OnlyHaveUniqueItems();
        lockWithRotatedOrder.StableIds.Should().OnlyHaveUniqueItems();
        lockWithOriginalOrder.StableIds.Should().BeEquivalentTo(lockWithRotatedOrder.StableIds,
            because: "stable_ids must be content-based and unchanged when only display_order changes");
    }

    // ACC:T4.9
    [Fact]
    public void Should_PreserveOfferLockingDataAcrossJsonRoundTrip_AndStayDeterministic_ForSameInput()
    {
        var serviceA = CreateOfferServiceForDeterminismTests();
        var serviceB = CreateOfferServiceForDeterminismTests();
        var provenance = CreateProvenance();
        var candidates = CreateCandidatesInDisplayOrder("offer.alpha", "offer.beta", "offer.gamma");

        var lockedByServiceA = serviceA.LockOffer("ctx-deterministic", candidates, provenance);
        var lockedByServiceB = serviceB.LockOffer("ctx-deterministic", candidates, provenance);

        var options = CreateDeterministicJsonOptions();
        var jsonBeforeRoundTrip = JsonSerializer.Serialize(lockedByServiceA, options);
        var roundTripped = JsonSerializer.Deserialize<OfferLockSnapshot>(jsonBeforeRoundTrip, options);

        roundTripped.Should().NotBeNull();
        roundTripped!.Should().BeEquivalentTo(lockedByServiceA);

        var jsonAfterRoundTrip = JsonSerializer.Serialize(roundTripped, options);
        jsonAfterRoundTrip.Should().Be(jsonBeforeRoundTrip);

        lockedByServiceB.StableIds.Should().Equal(lockedByServiceA.StableIds,
            because: "same input must produce stable deterministic stable_ids");
        lockedByServiceB.DisplayOrder.Should().Equal(lockedByServiceA.DisplayOrder,
            because: "same input must produce stable deterministic display_order");
        lockedByServiceB.Provenance.Should().Be(lockedByServiceA.Provenance);
        lockedByServiceB.RngStream.Should().Be(lockedByServiceA.RngStream);
    }

    private static IOfferService CreateOfferServiceForDeterminismTests()
    {
        var implementationCandidates = AppDomain.CurrentDomain
            .GetAssemblies()
            .SelectMany(GetLoadableTypes)
            .Where(type => typeof(IOfferService).IsAssignableFrom(type))
            .Where(type => type is { IsInterface: false, IsAbstract: false })
            .ToArray();

        implementationCandidates.Should().ContainSingle(
            because: "Task 4 requires one concrete IOfferService for deterministic lock behavior");

        var implementationType = implementationCandidates[0];
        var instance = TryCreateInstance(implementationType);

        instance.Should().NotBeNull(
            because: "the concrete offer service must be constructible for determinism checks");

        return instance.Should().BeAssignableTo<IOfferService>().Which;
    }

    private static object? TryCreateInstance(Type implementationType)
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
                if (!TryResolveConstructorArgument(parameters[index], out var argument))
                {
                    canResolveAll = false;
                    break;
                }

                arguments[index] = argument;
            }

            if (canResolveAll)
            {
                return constructor.Invoke(arguments);
            }
        }

        return null;
    }

    private static bool TryResolveConstructorArgument(ParameterInfo parameter, out object? argument)
    {
        if (parameter.HasDefaultValue)
        {
            argument = parameter.DefaultValue;
            return true;
        }

        if (parameter.ParameterType == typeof(IRngStreamRegistry))
        {
            argument = new DeterministicRngStreamRegistryStub();
            return true;
        }

        if (parameter.ParameterType == typeof(IEventBus))
        {
            argument = new NoOpEventBus();
            return true;
        }

        if (parameter.ParameterType == typeof(string))
        {
            argument = string.Empty;
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

    private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetTypes();
        }
        catch (ReflectionTypeLoadException ex)
        {
            return ex.Types
                .Where(type => type is not null)
                .Select(type => type!);
        }
    }

    private static OfferProvenance CreateProvenance()
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.2",
            Act: 2,
            Floor: 7,
            NodeId: "N-2-7",
            Difficulty: 4,
            RngStream: "reward.offer",
            StreamPosition: 128L);
    }

    private static IReadOnlyList<OfferItem> CreateCandidatesInDisplayOrder(params string[] offerItemIds)
    {
        return offerItemIds
            .Select((offerItemId, index) => new OfferItem(
                OfferItemId: offerItemId,
                CardId: $"card.{offerItemId}",
                Form: index % 2 == 0 ? CardForm.Base : CardForm.U1A,
                Route: index % 2 == 0 ? null : UpgradeRoute.A,
                Rarity: index % 2 == 0 ? "common" : "rare"))
            .ToArray();
    }

    private static JsonSerializerOptions CreateDeterministicJsonOptions()
    {
        return new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = false
        };
    }

    private sealed class DeterministicRngStreamRegistryStub : IRngStreamRegistry
    {
        public long GetPosition(string streamName) => 128L;

        public int NextInt(string streamName, int minInclusive, int maxExclusive) => minInclusive;

        public string Snapshot(string streamName) => "snapshot-fixed";

        public void Restore(string streamName, string snapshot)
        {
        }
    }

    private sealed class NoOpEventBus : IEventBus
    {
        public Task PublishAsync(DomainEvent evt) => Task.CompletedTask;

        public IDisposable Subscribe(Func<DomainEvent, Task> handler) => NoOpSubscription.Instance;

        private sealed class NoOpSubscription : IDisposable
        {
            public static readonly NoOpSubscription Instance = new();

            public void Dispose()
            {
            }
        }
    }
}
