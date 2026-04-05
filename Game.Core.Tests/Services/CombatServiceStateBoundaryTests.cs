using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Interfaces;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class CombatServiceStateBoundaryTests
{
    private sealed class CapturingEventBus : IEventBus
    {
        public List<DomainEvent> Published { get; } = new();

        public Task PublishAsync(DomainEvent evt)
        {
            Published.Add(evt);
            return Task.CompletedTask;
        }

        public IDisposable Subscribe(Func<DomainEvent, Task> handler)
        {
            return new DummySubscription();
        }

        private sealed class DummySubscription : IDisposable
        {
            public void Dispose()
            {
            }
        }
    }

    // ACC:T11.23
    [Fact]
    public void ShouldFailAndKeepStateUnchanged_WhenOutOfBoundaryStepFailureIsInjected()
    {
        var service = new CombatService();
        var input = CreateValidPipelineInput(failAtStep: PlayCardPipelineStep.AfterPlayTriggers);

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeFalse();
        result.ExecutedSteps.Should().Equal(
            PlayCardPipelineStep.Validate,
            PlayCardPipelineStep.ComputeCost,
            PlayCardPipelineStep.PayCost,
            PlayCardPipelineStep.BeforePlayTriggers,
            PlayCardPipelineStep.ResolveEffect,
            PlayCardPipelineStep.AfterPlayTriggers);
        result.StateAfter.Should().Be(result.StateBefore);
        result.FailureReason.Should().Contain("Injected failure at AfterPlayTriggers");
    }

    // ACC:T11.24
    [Fact]
    public void ShouldEmitAuditableBoundaryTrailInStableOrder_WhenPipelineSucceeds()
    {
        var bus = new CapturingEventBus();
        var service = new CombatService(bus);
        var input = CreateValidPipelineInput();

        var result = service.ExecutePlayCardPipeline(input);

        result.Success.Should().BeTrue();

        var boundaryTrail = bus.Published
            .Where(evt => evt.Type == EventTypes.AuditLogged && evt.Source == nameof(CombatService))
            .Select(ExtractPhaseFromAuditEvent)
            .OfType<string>()
            .ToArray();

        boundaryTrail.Should().Equal(
            "BeforePlayTriggers",
            "ResolveEffect",
            "AfterPlayTriggers");
    }

    private static string? ExtractPhaseFromAuditEvent(DomainEvent evt)
    {
        if (string.IsNullOrWhiteSpace(evt.DataJson))
        {
            return null;
        }

        using var doc = JsonDocument.Parse(evt.DataJson);
        if (!doc.RootElement.TryGetProperty("phase", out var phase))
        {
            return null;
        }

        return phase.GetString();
    }

    private static PlayCardPipelineInput CreateValidPipelineInput(
        int difficultyId = 10,
        int cardsPlayedThisTurn = 2,
        int overplayTriggerN = 3,
        int overplayTaxPerCard = 2,
        int baseCardCost = 1,
        int energyBefore = 10,
        int baseDamage = 12,
        int strength = 2,
        double weakMultiplier = 1.0,
        double vulnerableMultiplier = 1.0,
        bool isFixedDamage = false,
        string combatantId = "combatant-a",
        string stableId = "stable-001",
        PlayCardPipelineStep? failAtStep = null)
    {
        return new PlayCardPipelineInput(
            DifficultyId: difficultyId,
            CardsPlayedThisTurn: cardsPlayedThisTurn,
            OverplayTriggerN: overplayTriggerN,
            OverplayTaxPerCard: overplayTaxPerCard,
            BaseCardCost: baseCardCost,
            EnergyBefore: energyBefore,
            BaseDamage: baseDamage,
            Strength: strength,
            WeakMultiplier: weakMultiplier,
            VulnerableMultiplier: vulnerableMultiplier,
            IsFixedDamage: isFixedDamage,
            CombatantId: combatantId,
            StableId: stableId,
            FailAtStep: failAtStep);
    }
}
