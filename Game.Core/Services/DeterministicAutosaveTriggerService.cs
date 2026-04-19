using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;

namespace Game.Core.Services;

/// <summary>
/// Applies deterministic autosave trigger policy for run progression events.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0023.
/// </remarks>
public sealed class DeterministicAutosaveTriggerService
{
    private readonly ISaveService saveService;
    private readonly Func<AutosaveTriggerContext, AutosaveSnapshot> snapshotFactory;
    private readonly HashSet<string> rewardFirstShownKeys = new(StringComparer.Ordinal);
    private long sequence;

    public DeterministicAutosaveTriggerService(
        ISaveService saveService,
        Func<AutosaveTriggerContext, AutosaveSnapshot> snapshotFactory)
    {
        this.saveService = saveService ?? throw new ArgumentNullException(nameof(saveService));
        this.snapshotFactory = snapshotFactory ?? throw new ArgumentNullException(nameof(snapshotFactory));
    }

    public Task HandleCombatStartedAsync(CombatStartedEvent @event)
    {
        ArgumentNullException.ThrowIfNull(@event);
        return PersistAsync(
            trigger: "BattleEnteredInitialState",
            runId: @event.RunId,
            sourceId: @event.CombatId,
            occurredAt: @event.StartedAt);
    }

    public Task HandleRewardOfferLockedAsync(RewardOfferLockedEvent @event)
    {
        ArgumentNullException.ThrowIfNull(@event);

        var dedupeKey = string.Concat(@event.RunId, "|", @event.OfferContextId);
        if (!rewardFirstShownKeys.Add(dedupeKey))
        {
            return Task.CompletedTask;
        }

        return PersistAsync(
            trigger: "RewardScreenFirstShown",
            runId: @event.RunId,
            sourceId: @event.OfferContextId,
            occurredAt: @event.LockedAt);
    }

    public Task HandleEventChoiceCommittedAsync(EventChoiceCommittedEvent @event)
    {
        ArgumentNullException.ThrowIfNull(@event);
        return PersistAsync(
            trigger: "EventChoiceCommitted",
            runId: @event.RunId,
            sourceId: @event.EventId,
            occurredAt: @event.CommittedAt);
    }

    public Task HandleSkipFlowStartedAsync(string runId, DateTimeOffset occurredAt)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(runId);
        _ = occurredAt;
        return Task.CompletedTask;
    }

    public Task HandleSkipFlowCompletedAsync(string runId, DateTimeOffset occurredAt)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(runId);
        _ = occurredAt;
        return Task.CompletedTask;
    }

    private Task PersistAsync(string trigger, string runId, string sourceId, DateTimeOffset occurredAt)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(trigger);
        ArgumentException.ThrowIfNullOrWhiteSpace(runId);
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceId);

        sequence++;
        var context = new AutosaveTriggerContext(
            Trigger: trigger,
            RunId: runId,
            SourceId: sourceId,
            Sequence: sequence,
            OccurredAt: occurredAt);
        var snapshot = snapshotFactory(context);
        return saveService.WriteAutosaveAsync(snapshot);
    }
}

public sealed record AutosaveTriggerContext(
    string Trigger,
    string RunId,
    string SourceId,
    long Sequence,
    DateTimeOffset OccurredAt);
