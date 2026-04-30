using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;

namespace Game.Core.Services;

/// <summary>
/// Shared run-path relic ownership and equip visibility service.
/// Ownership is tracked by the existing inventory service.
/// </summary>
public sealed class RunRelicStateService
{
    private readonly InventoryService _inventoryService;
    private readonly Func<string, string> _displayNameResolver;
    private readonly IEventBus? _eventBus;
    private readonly Action<string, Exception>? _publishFailureObserver;
    private readonly IReadOnlySet<string>? _validRelicIdSet;
    private string _equippedRelicId = string.Empty;

    public RunRelicStateService(
        InventoryService inventoryService,
        Func<string, string>? displayNameResolver = null,
        IEventBus? eventBus = null,
        Action<string, Exception>? publishFailureObserver = null,
        IReadOnlySet<string>? validRelicIdSet = null)
    {
        _inventoryService = inventoryService ?? throw new ArgumentNullException(nameof(inventoryService));
        _displayNameResolver = displayNameResolver ?? (id => id);
        _eventBus = eventBus;
        _publishFailureObserver = publishFailureObserver;
        _validRelicIdSet = validRelicIdSet;
    }

    public bool TryGrantAndEquip(string relicId)
    {
        var normalized = NormalizeRelicId(relicId);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return false;
        }

        if (!IsDefinedRelicId(normalized))
        {
            return false;
        }

        if (_inventoryService.HasItem(normalized, atLeast: 1))
        {
            return false;
        }

        var added = _inventoryService.Add(normalized, count: 1, maxStack: 1);
        if (added != 1)
        {
            return false;
        }

        _equippedRelicId = normalized;
        PublishRelicGranted(normalized, "task-88", "shared-run-path");
        PublishRelicEquipped(normalized, "grant");
        return true;
    }

    public bool TryEquipExisting(string relicId)
    {
        var normalized = NormalizeRelicId(relicId);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return false;
        }

        if (!IsDefinedRelicId(normalized))
        {
            return false;
        }

        if (!_inventoryService.HasItem(normalized, atLeast: 1))
        {
            return false;
        }

        _equippedRelicId = normalized;
        PublishRelicEquipped(normalized, "equip");
        return true;
    }

    public void ClearEquipped()
    {
        _equippedRelicId = string.Empty;
    }

    public RunRelicSnapshot CreateSnapshot()
    {
        var acquired = _inventoryService.GetItemIds()
            .Where(IsRelicId)
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();

        var equippedId = _equippedRelicId;
        if (!string.IsNullOrWhiteSpace(equippedId) && !_inventoryService.HasItem(equippedId, atLeast: 1))
        {
            equippedId = string.Empty;
        }

        var equippedDisplay = string.IsNullOrWhiteSpace(equippedId)
            ? string.Empty
            : _displayNameResolver(equippedId);

        return new RunRelicSnapshot(acquired, equippedId, equippedDisplay);
    }

    private static string NormalizeRelicId(string relicId)
    {
        var normalized = (relicId ?? string.Empty).Trim();
        if (!IsRelicId(normalized))
        {
            return string.Empty;
        }

        return normalized;
    }

    private bool IsDefinedRelicId(string relicId)
    {
        if (_validRelicIdSet is null)
        {
            return true;
        }

        return _validRelicIdSet.Contains(relicId);
    }

    private static bool IsRelicId(string relicId)
    {
        return !string.IsNullOrWhiteSpace(relicId)
            && relicId.StartsWith("relic.", StringComparison.Ordinal);
    }

    private void PublishRelicGranted(string relicId, string sourceType, string sourceId)
    {
        if (_eventBus is null)
        {
            return;
        }

        var payload = JsonSerializer.Serialize(new
        {
            relic_id = relicId,
            source_type = sourceType,
            source_id = sourceId,
        });
        var evt = new DomainEvent(
            EventTypes.RelicGranted,
            nameof(RunRelicStateService),
            payload,
            DateTimeOffset.UtcNow,
            Guid.NewGuid().ToString("N"));
        _ = PublishWithoutBlockingAsync(EventTypes.RelicGranted, evt);
    }

    private void PublishRelicEquipped(string relicId, string reason)
    {
        if (_eventBus is null)
        {
            return;
        }

        var payload = JsonSerializer.Serialize(new
        {
            relic_id = relicId,
            reason,
        });
        var evt = new DomainEvent(
            EventTypes.RelicEquipped,
            nameof(RunRelicStateService),
            payload,
            DateTimeOffset.UtcNow,
            Guid.NewGuid().ToString("N"));
        _ = PublishWithoutBlockingAsync(EventTypes.RelicEquipped, evt);
    }

    private async Task PublishWithoutBlockingAsync(string eventType, DomainEvent evt)
    {
        if (_eventBus is null)
        {
            return;
        }

        try
        {
            await _eventBus.PublishAsync(evt).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            // Keep relic-state transitions stable even when event subscribers fail.
            _publishFailureObserver?.Invoke(eventType, ex);
        }
    }
}

public sealed record RunRelicSnapshot(
    IReadOnlyList<string> AcquiredRelicIds,
    string EquippedRelicId,
    string EquippedDisplayName);
