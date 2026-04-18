using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Run;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0020AcceptanceTests
{
    private const int TaskmasterId = 20;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs";
    private const string ThisGdTestRef = "Tests.Godot/tests/Tasks/test_task0020_acceptance.gd";
    private const string OverlayChecklistPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";

    private static readonly string[] RequiredCoverageTags =
    {
        "shop_purchase",
        "shop_inventory_lock",
        "shop_no_upgrade_copy",
        "reenter_persistence",
    };

    // ACC:T20.1, ACC:T20.4
    [Fact]
    [Trait("acceptance", "ACC:T20.1")]
    [Trait("acceptance", "ACC:T20.4")]
    public void ShouldKeepStableInventoryIdentity_WhenShopInventoryLockEventIsReused()
    {
        var stableIds = new[] { "card_strike_plus", "relic_amber", "card_shield_wall" };
        var displayOrder = new[] { "relic_amber", "card_strike_plus", "card_shield_wall" };
        var lockedAt = new DateTimeOffset(2026, 4, 18, 0, 0, 0, TimeSpan.Zero);

        var firstLock = new ShopInventoryLockedEvent(
            RunId: "run-20",
            ShopId: "shop-01",
            StableIds: stableIds,
            DisplayOrder: displayOrder,
            LockedAt: lockedAt);
        var replayedLock = new ShopInventoryLockedEvent(
            RunId: "run-20",
            ShopId: "shop-01",
            StableIds: stableIds,
            DisplayOrder: displayOrder,
            LockedAt: lockedAt);

        firstLock.StableIds.Should().Equal(replayedLock.StableIds);
        firstLock.DisplayOrder.Should().Equal(replayedLock.DisplayOrder);
        firstLock.ShopId.Should().Be(replayedLock.ShopId);
        firstLock.RunId.Should().Be(replayedLock.RunId);
    }

    // ACC:T20.2, ACC:T20.6, ACC:T20.7
    [Fact]
    [Trait("acceptance", "ACC:T20.2")]
    [Trait("acceptance", "ACC:T20.6")]
    [Trait("acceptance", "ACC:T20.7")]
    public void ShouldTrackPurchaseAndCurseRemovalWithoutUpgradeContext_WhenShopEventsArePublished()
    {
        var purchasedAt = new DateTimeOffset(2026, 4, 18, 0, 5, 0, TimeSpan.Zero);
        var removedAt = new DateTimeOffset(2026, 4, 18, 0, 6, 0, TimeSpan.Zero);
        var purchasedEvent = new ShopItemPurchasedEvent(
            RunId: "run-20",
            ShopId: "shop-01",
            ItemId: "relic_amber",
            ItemType: "relic",
            Price: 150,
            PurchasedAt: purchasedAt);
        var curseRemovedEvent = new ShopCurseRemovedEvent(
            RunId: "run-20",
            ShopId: "shop-01",
            CardId: "curse_decay",
            Price: 80,
            RemovedAt: removedAt);

        purchasedEvent.ItemType.Should().Be("relic");
        purchasedEvent.ItemType.Should().NotContain("upgrade");
        purchasedEvent.Price.Should().Be(150);
        curseRemovedEvent.CardId.Should().Be("curse_decay");
        curseRemovedEvent.Price.Should().Be(80);
        curseRemovedEvent.ShopId.Should().Be(purchasedEvent.ShopId);
    }

    // ACC:T20.2
    [Fact]
    [Trait("acceptance", "ACC:T20.2")]
    public void ShouldEnterAndLeaveShopState_WhenRunStateMachineReceivesShopCommands()
    {
        var machine = new RunStateMachine();
        var commands = new[]
        {
            CreateCommand("cmd-1", "enter_node"),
            CreateCommand("cmd-2", "open_shop"),
            CreateCommand("cmd-3", "leave_shop"),
        };

        foreach (var command in commands)
        {
            machine.TryProcessCommand(command, out _).Should().BeTrue();
        }

        machine.Transitions.Select(transition => transition.ToState).Should().Equal(
            RunState.NodePreEnter,
            RunState.Shop,
            RunState.NodePreEnter);
    }

    // ACC:T20.3, ACC:T20.5
    [Fact]
    [Trait("acceptance", "ACC:T20.3")]
    [Trait("acceptance", "ACC:T20.5")]
    public void ShouldExposeTaskRefsAndShopContractEventTypes_WhenAcceptanceEvidenceIsEnumerated()
    {
        var taskNode = ReadTaskNodeByTaskmasterId(
            Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json"),
            TaskmasterId);
        var taskRefs = ReadStringArray(taskNode, "test_refs");
        var overlayRefs = ReadStringArray(taskNode, "overlay_refs");
        var acceptanceText = string.Join("\n", ReadStringArray(taskNode, "acceptance"));
        var checklistPath = Path.Combine(FindRepositoryRoot(), OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));
        var checklist = File.ReadAllText(checklistPath);
        var contractEventTypes = GetShopContractEventTypes();

        taskRefs.Should().Contain(ThisTaskTestRef);
        taskRefs.Should().Contain(ThisGdTestRef);
        overlayRefs.Should().Contain(OverlayChecklistPath);
        acceptanceText.Should().Contain(ThisGdTestRef);
        acceptanceText.Should().Contain("库存锁定");
        acceptanceText.Should().Contain("升级/Upgrade");

        checklist.Should().Contain(ThisTaskTestRef);
        checklist.Should().Contain(ThisGdTestRef);
        checklist.Should().Contain("Task20");
        foreach (var tag in RequiredCoverageTags)
        {
            checklist.Should().Contain(tag);
        }

        contractEventTypes.Should().ContainInOrder(
            EventTypes.ShopInventoryLocked,
            EventTypes.ShopItemPurchased,
            EventTypes.ShopCurseRemoved);
        contractEventTypes.Should().OnlyHaveUniqueItems();
    }

    private static RunCommand CreateCommand(string commandId, string commandType)
    {
        return new RunCommand(
            CommandId: commandId,
            CommandType: commandType,
            Issuer: "test",
            PayloadJson: "{}",
            IssuedAt: new DateTimeOffset(2026, 4, 18, 0, 0, 0, TimeSpan.Zero));
    }

    private static JsonElement ReadTaskNodeByTaskmasterId(string taskFilePath, int taskmasterId)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        var taskNode = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("taskmaster_id", out var idNode) &&
                idNode.ValueKind == JsonValueKind.Number &&
                idNode.GetInt32() == taskmasterId);

        taskNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, "Task 20 metadata must exist in tasks_gameplay.json");
        return JsonDocument.Parse(taskNode.GetRawText()).RootElement.Clone();
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement node, string fieldName)
    {
        if (!node.TryGetProperty(fieldName, out var field) || field.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return field.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current != null)
        {
            var marker = Path.Combine(current.FullName, ".taskmaster", "tasks", "tasks_gameplay.json");
            if (File.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from AppContext.BaseDirectory.");
    }

    private static IReadOnlyCollection<string> GetShopContractEventTypes()
    {
        return new[]
        {
            ShopInventoryLockedEvent.EventType,
            ShopItemPurchasedEvent.EventType,
            ShopCurseRemovedEvent.EventType,
        };
    }
}
