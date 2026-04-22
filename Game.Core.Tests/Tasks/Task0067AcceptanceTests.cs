using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Run;
using Game.Core.Services;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0067AcceptanceTests
{
    private const int TaskmasterId = 67;
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0067AcceptanceTests.cs";
    private const string ShopSceneBindingTestRef = "Tests.Godot/tests/Scenes/Shop/test_shop_scene_behavior_binding.gd";
    private const string ShopScenePath = "Game.Godot/Scenes/Shop.tscn";

    private static readonly MapNodeRouteOwnershipService RouteService = new();

    // ACC:T67.1
    [Fact]
    [Trait("acceptance", "ACC:T67.1")]
    public void ShouldBindRealOwnedShopActions_WhenInspectingTheActualShopScene()
    {
        var shopScene = ReadRepositoryFile(ShopScenePath);

        shopScene.Should().Contain("name=\"OfferList\"", "the actual Shop scene must expose purchasable offers from the real UI");
        shopScene.Should().Contain("name=\"RemoveButton\"", "the actual Shop scene must expose a remove action");
        shopScene.Should().Contain("name=\"ReforgeButton\"", "the actual Shop scene must expose a transform or reforge action");
        shopScene.Should().Contain("script = ExtResource(", "the actual Shop scene must be bound to real owned behavior instead of static placeholder layout only");
        shopScene.Should().Contain("name=\"LeaveButton\"", "the actual Shop scene must let the player leave through the Shop-owned route");
    }

    // ACC:T67.2
    [Fact]
    [Trait("acceptance", "ACC:T67.2")]
    public void ShouldExposeObservableShopStateAndVisibleFailureReason_WhenInspectingTheActualShopScene()
    {
        var normalizedScene = ReadRepositoryFile(ShopScenePath).ToLowerInvariant();

        normalizedScene.Should().Contain("offerlist", "the Shop UI must show current offers");
        normalizedScene.Should().Contain("gold", "the Shop UI must show current player resources");
        normalizedScene.Should().Contain("price", "the Shop UI must show prices for real shop actions");
        normalizedScene.Should().Contain("owned", "the Shop UI must expose owned or purchased outcomes");
        normalizedScene.Should().Contain("removed", "the Shop UI must expose removed outcomes for shop services");
        normalizedScene.Should().Contain("failure", "the Shop UI must show visible failure feedback");
        normalizedScene.Should().Contain("insufficient", "the Shop UI must explain when purchase fails because resources are insufficient");
        normalizedScene.Should().Contain("taken", "the Shop UI must explain when purchase fails because the offer was already taken");
    }

    // ACC:T67.4
    [Fact]
    [Trait("acceptance", "ACC:T67.4")]
    public void ShouldKeepShopTextWithinShopSemantics_WhenEnumeratingShopSceneTextAndContracts()
    {
        var normalizedText = string.Join("\n", ReadSceneTextAssignments(ShopScenePath)).ToLowerInvariant();

        normalizedText.Should().Contain("shop.title");
        normalizedText.Should().Contain("shop.service.remove");
        normalizedText.Should().Contain("shop.service.reforge");
        normalizedText.Should().NotContain("upgrade");
        normalizedText.Should().NotContain("rest");
        normalizedText.Should().NotContain("campfire");
        normalizedText.Should().NotContain("card-upgrade");

        EventTypes.ShopInventoryLocked.Should().StartWith("core.shop.");
        EventTypes.ShopItemPurchased.Should().StartWith("core.shop.");
        EventTypes.ShopCurseRemoved.Should().StartWith("core.shop.");
    }

    // ACC:T67.6
    [Fact]
    [Trait("acceptance", "ACC:T67.6")]
    public void ShouldRequireRealSceneBindingEvidence_WhenReadingTaskAcceptanceRefs()
    {
        var taskFilePath = Path.Combine(FindRepositoryRoot(), ".taskmaster", "tasks", "tasks_gameplay.json");
        var taskNode = ReadTaskNodeByTaskmasterId(taskFilePath, TaskmasterId);
        var acceptance = ReadStringArray(taskNode, "acceptance");
        var testRefs = ReadStringArray(taskNode, "test_refs");
        var shopScene = ReadRepositoryFile(ShopScenePath);

        testRefs.Should().Contain(ShopSceneBindingTestRef);
        testRefs.Should().Contain(ThisTaskTestRef);
        acceptance.Should().Contain(item => item.Contains(ShopSceneBindingTestRef, StringComparison.Ordinal));
        acceptance.Should().Contain(item => item.Contains(ThisTaskTestRef, StringComparison.Ordinal));
        shopScene.Should().Contain("[gd_scene format=3]");
    }

    // ACC:T67.7
    [Fact]
    [Trait("acceptance", "ACC:T67.7")]
    public void ShouldRoundTripThroughSharedRouteOwnership_WhenLeavingShopAfterMapEntry()
    {
        var initialProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 0);
        var selectedNode = new MapNodeRouteRequest("shop-01", "shop", IsReachable: true);
        var enterResult = RouteService.StartRoute(selectedNode, initialProgress);
        var returnResult = RouteService.CompleteRoute(enterResult.NewProgress);

        var machine = new RunStateMachine(RunState.NodePreEnter);
        var openCommand = CreateCommand("cmd-67-open-shop", "open_shop");
        var leaveCommand = CreateCommand("cmd-67-leave-shop", "leave_shop");

        var openAccepted = machine.TryProcessCommand(openCommand, out var openTransition);
        var leaveAccepted = machine.TryProcessCommand(leaveCommand, out var leaveTransition);

        openAccepted.Should().BeTrue();
        leaveAccepted.Should().BeTrue();
        enterResult.IsSuccess.Should().BeTrue();
        enterResult.Destination.Should().Be(MapNodeRouteDestination.Shop);
        enterResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Shop);
        returnResult.IsSuccess.Should().BeTrue();
        returnResult.Destination.Should().Be(MapNodeRouteDestination.Map);
        returnResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        returnResult.NewProgress.CompletedNodeCount.Should().Be(1);
        openTransition.ToState.Should().Be(RunState.Shop);
        leaveTransition.FromState.Should().Be(RunState.Shop);
        leaveTransition.ToState.Should().Be(RunState.NodePreEnter);
    }

    [Fact]
    public void ShouldRefuseSecondMapEntry_WhenShopAlreadyOwnsTheActiveRoute()
    {
        var activeProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Shop, CompletedNodeCount: 2);
        var selectedNode = new MapNodeRouteRequest("shop-02", "shop", IsReachable: true);

        var result = RouteService.StartRoute(selectedNode, activeProgress);

        result.IsSuccess.Should().BeFalse();
        result.BlockReason.Should().Be("route-owner-mismatch");
        result.NewProgress.Should().Be(activeProgress);
        result.Destination.Should().Be(MapNodeRouteDestination.Shop);
    }

    private static string ReadRepositoryFile(string relativePath)
    {
        var fullPath = Path.Combine(FindRepositoryRoot(), relativePath.Replace('/', Path.DirectorySeparatorChar));
        return File.ReadAllText(fullPath);
    }

    private static IReadOnlyList<string> ReadSceneTextAssignments(string relativePath)
    {
        return ReadRepositoryFile(relativePath)
            .Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(line => line.Trim())
            .Where(line => line.StartsWith("text = ", StringComparison.Ordinal))
            .ToArray();
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

        taskNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, "Task 67 metadata must exist in tasks_gameplay.json");
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

    private static RunCommand CreateCommand(string commandId, string commandType)
    {
        return new RunCommand(
            CommandId: commandId,
            CommandType: commandType,
            Issuer: "test",
            PayloadJson: "{}",
            IssuedAt: new DateTimeOffset(2026, 4, 22, 0, 0, 0, TimeSpan.Zero));
    }
}
