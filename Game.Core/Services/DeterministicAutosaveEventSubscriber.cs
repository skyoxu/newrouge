using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;

namespace Game.Core.Services;

/// <summary>
/// Bridges domain events to deterministic autosave trigger service.
/// </summary>
public sealed class DeterministicAutosaveEventSubscriber : IDisposable
{
    private readonly IDisposable subscription;
    private readonly DeterministicAutosaveTriggerService triggerService;

    public DeterministicAutosaveEventSubscriber(
        IEventBus eventBus,
        DeterministicAutosaveTriggerService triggerService)
    {
        ArgumentNullException.ThrowIfNull(eventBus);
        this.triggerService = triggerService ?? throw new ArgumentNullException(nameof(triggerService));
        subscription = eventBus.Subscribe(OnDomainEventAsync);
    }

    public void Dispose()
    {
        subscription.Dispose();
    }

    private Task OnDomainEventAsync(DomainEvent evt)
    {
        if (string.IsNullOrWhiteSpace(evt.DataJson))
        {
            return Task.CompletedTask;
        }

        return evt.Type switch
        {
            EventTypes.CombatStarted => HandleCombatStartedAsync(evt),
            EventTypes.RewardOfferLocked => HandleRewardOfferLockedAsync(evt),
            EventTypes.EventChoiceCommitted => HandleEventChoiceCommittedAsync(evt),
            _ => Task.CompletedTask,
        };
    }

    private Task HandleCombatStartedAsync(DomainEvent evt)
    {
        using var doc = JsonDocument.Parse(evt.DataJson!);
        var root = doc.RootElement;
        var runId = ReadString(root, "run_id") ?? ReadString(root, "RunId");
        var combatId = ReadString(root, "combat_id") ?? ReadString(root, "CombatId");
        var turn = ReadInt(root, "turn") ?? ReadInt(root, "Turn") ?? 1;
        if (string.IsNullOrWhiteSpace(runId) || string.IsNullOrWhiteSpace(combatId))
        {
            return Task.CompletedTask;
        }

        return triggerService.HandleCombatStartedAsync(new CombatStartedEvent(
            RunId: runId,
            CombatId: combatId,
            Turn: turn,
            StartedAt: evt.Timestamp));
    }

    private Task HandleRewardOfferLockedAsync(DomainEvent evt)
    {
        using var doc = JsonDocument.Parse(evt.DataJson!);
        var root = doc.RootElement;
        var runId = ReadString(root, "run_id") ?? ReadString(root, "RunId");
        var contextId = ReadString(root, "offer_context_id") ?? ReadString(root, "OfferContextId");
        if (string.IsNullOrWhiteSpace(runId) || string.IsNullOrWhiteSpace(contextId))
        {
            return Task.CompletedTask;
        }

        var stableIds = ReadStringArray(root, "stable_ids", "StableIds");
        var displayOrder = ReadStringArray(root, "display_order", "DisplayOrder");

        return triggerService.HandleRewardOfferLockedAsync(new RewardOfferLockedEvent(
            RunId: runId,
            OfferContextId: contextId,
            StableIds: stableIds,
            DisplayOrder: displayOrder,
            LockedAt: evt.Timestamp));
    }

    private Task HandleEventChoiceCommittedAsync(DomainEvent evt)
    {
        using var doc = JsonDocument.Parse(evt.DataJson!);
        var root = doc.RootElement;
        var runId = ReadString(root, "run_id") ?? ReadString(root, "RunId");
        var eventId = ReadString(root, "event_id") ?? ReadString(root, "EventId");
        var optionId = ReadString(root, "option_id") ?? ReadString(root, "OptionId");
        var resultId = ReadString(root, "result_id") ?? ReadString(root, "ChoiceResultId");
        if (string.IsNullOrWhiteSpace(runId)
            || string.IsNullOrWhiteSpace(eventId)
            || string.IsNullOrWhiteSpace(optionId)
            || string.IsNullOrWhiteSpace(resultId))
        {
            return Task.CompletedTask;
        }

        return triggerService.HandleEventChoiceCommittedAsync(new EventChoiceCommittedEvent(
            RunId: runId,
            EventId: eventId,
            OptionId: optionId,
            ChoiceResultId: resultId,
            CommittedAt: evt.Timestamp));
    }

    private static string? ReadString(JsonElement root, string propertyName)
    {
        if (!root.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        var text = value.GetString();
        return string.IsNullOrWhiteSpace(text) ? null : text;
    }

    private static int? ReadInt(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out var output)
            ? output
            : null;
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement root, string primaryName, string fallbackName)
    {
        JsonElement arrayNode;
        if (root.TryGetProperty(primaryName, out var primary) && primary.ValueKind == JsonValueKind.Array)
        {
            arrayNode = primary;
        }
        else if (root.TryGetProperty(fallbackName, out var fallback) && fallback.ValueKind == JsonValueKind.Array)
        {
            arrayNode = fallback;
        }
        else
        {
            return Array.Empty<string>();
        }

        return arrayNode
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
    }
}
