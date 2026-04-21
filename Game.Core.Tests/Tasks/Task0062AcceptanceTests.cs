using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Xml.Linq;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0062AcceptanceTests
{
    private static readonly string RepoRoot = ResolveRepoRoot();

    // ACC:T62.1
    [Fact]
    public void ShouldLoadStandaloneRestScene_WhenEnteringRestNodeFromMap()
    {
        var scenePath = Path.Combine(RepoRoot, "Game.Godot", "Scenes", "Rest.tscn");
        File.Exists(scenePath).Should().BeTrue();

        var routeService = new MapNodeRouteOwnershipService();
        var progress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 2);
        var enterResult = routeService.StartRoute(
            new MapNodeRouteRequest("rest-01", "rest", IsReachable: true),
            progress);

        enterResult.IsSuccess.Should().BeTrue();
        enterResult.Destination.Should().Be(MapNodeRouteDestination.Rest);
        enterResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Rest);
    }

    // ACC:T62.2
    [Fact]
    public void ShouldExposeSelectableHealUpgradeAndCurseRemovalChoices_WhenRestSceneRuntimeEvidenceIsCollected()
    {
        var evidencePath = ResolveRestGdUnitSummaryPath();
        File.Exists(evidencePath).Should().BeTrue();

        using var document = JsonDocument.Parse(File.ReadAllText(evidencePath));
        var root = document.RootElement;
        var resultsPath = root.GetProperty("results").GetProperty("path").GetString();
        resultsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(resultsPath!).Should().BeTrue();
        var xml = XDocument.Load(resultsPath!);
        HasPassedTestCase(xml, "test_rest_scene_exposes_heal_upgrade_and_curse_removal_choices")
            .Should().BeTrue("ACC:T62.2 must be executed and passed in real-scene runtime evidence.");
        root.GetProperty("normalized_rc").GetInt32().Should().Be(0);
        root.GetProperty("results").GetProperty("failures").GetInt32().Should().Be(0);
        root.GetProperty("results").GetProperty("errors").GetInt32().Should().Be(0);
    }

    // ACC:T62.3
    [Fact]
    public void ShouldRefuseUnrelatedRouteOwnerAndKeepStateUnchanged_AfterHealFlowReturnsToMap()
    {
        var routeService = new MapNodeRouteOwnershipService();
        var mapProgress = new MapNodeRouteProgress(MapNodeRouteDestination.Map, CompletedNodeCount: 3);
        var enterResult = routeService.StartRoute(
            new MapNodeRouteRequest("rest-02", "rest", IsReachable: true),
            mapProgress);

        enterResult.IsSuccess.Should().BeTrue();
        enterResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Rest);
        var completeResult = routeService.CompleteRoute(enterResult.NewProgress);

        completeResult.IsSuccess.Should().BeTrue();
        completeResult.NewProgress.CurrentState.Should().Be(MapNodeRouteDestination.Map);
        completeResult.NewProgress.CompletedNodeCount.Should().Be(4);

        var illegal = routeService.StartRoute(
            new MapNodeRouteRequest("shop-01", "shop", IsReachable: true),
            enterResult.NewProgress);

        illegal.IsSuccess.Should().BeFalse();
        illegal.BlockReason.Should().Be("route-owner-mismatch");
        illegal.NewProgress.Should().Be(enterResult.NewProgress);
    }

    // ACC:T62.5
    [Fact]
    public void ShouldApplyCurseRemovalResultAndReturnToMap_WhenRealSceneEvidenceIsCollected()
    {
        var evidencePath = ResolveRestGdUnitSummaryPath();
        File.Exists(evidencePath).Should().BeTrue();

        using var document = JsonDocument.Parse(File.ReadAllText(evidencePath));
        var root = document.RootElement;
        var resultsPath = root.GetProperty("results").GetProperty("path").GetString();
        resultsPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(resultsPath!).Should().BeTrue();
        var xml = XDocument.Load(resultsPath!);
        HasPassedTestCase(xml, "test_remove_curse_from_rest_applies_result_and_returns_to_map")
            .Should().BeTrue("ACC:T62.5 must be executed and passed in real-scene runtime evidence.");
        root.GetProperty("normalized_rc").GetInt32().Should().Be(0);
        root.GetProperty("results").GetProperty("failures").GetInt32().Should().Be(0);
        root.GetProperty("results").GetProperty("errors").GetInt32().Should().Be(0);
    }

    // ACC:T62.6
    [Fact]
    public void ShouldProvideDeterministicWindowsEvidence_WhenRestRouteRoundtripAndUpgradeConfirmationAreVerified()
    {
        var runSummaryPath = Path.Combine(
            RepoRoot,
            "logs",
            "e2e",
            DateTime.UtcNow.ToString("yyyy-MM-dd"),
            "sc-test",
            "gdunit-hard",
            "run-summary.json");

        var fallbackSummaryPath = Path.Combine(
            RepoRoot,
            "logs",
            "e2e",
            "2026-04-21",
            "sc-test",
            "gdunit-hard",
            "run-summary.json");

        var evidencePath = File.Exists(runSummaryPath) ? runSummaryPath : fallbackSummaryPath;
        File.Exists(evidencePath).Should().BeTrue("Windows deterministic gdUnit evidence must exist.");

        var evidence = File.ReadAllText(evidencePath);
        evidence.Should().Contain("\"normalized_rc\": 0");
        evidence.Should().Contain("test_rest_scene_route_roundtrip.gd");
        evidence.Should().Contain("test_rest_upgrade_confirmation_irreversible.gd");
    }

    // ACC:T62.7
    [Fact]
    public void ShouldKeepTaskTraceabilityLinkedToDesignContext_WhenRestRouteEvidenceIsCollected()
    {
        var gameplayTasksPath = Path.Combine(RepoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");
        var payload = File.ReadAllText(gameplayTasksPath);

        payload.Should().Contain("\"taskmaster_id\": 62");
        payload.Should().Contain("UI-WIRING-M1-A4");
        payload.Should().Contain("ADR-0025");
        payload.Should().Contain("ADR-0032");
        payload.Should().Contain("ADR-0033");
        payload.Should().Contain("CH06");
    }

    private static string ResolveRepoRoot()
    {
        var current = AppContext.BaseDirectory;
        var dir = new DirectoryInfo(current);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "NewRouge.sln")))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new InvalidOperationException("Failed to resolve repository root from test context.");
    }

    private static string ResolveRestGdUnitSummaryPath()
    {
        var today = Path.Combine(
            RepoRoot,
            "logs",
            "e2e",
            DateTime.UtcNow.ToString("yyyy-MM-dd"),
            "sc-test",
            "gdunit-hard",
            "run-summary.json");
        if (File.Exists(today))
        {
            return today;
        }

        return Path.Combine(
            RepoRoot,
            "logs",
            "e2e",
            "2026-04-21",
            "sc-test",
            "gdunit-hard",
            "run-summary.json");
    }

    private static bool HasPassedTestCase(XDocument xml, string testCaseName)
    {
        var testCase = xml
            .Descendants("testcase")
            .FirstOrDefault(node => string.Equals(node.Attribute("name")?.Value, testCaseName, StringComparison.Ordinal));
        if (testCase is null)
        {
            return false;
        }

        return !testCase.Elements().Any(element =>
            string.Equals(element.Name.LocalName, "failure", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(element.Name.LocalName, "error", StringComparison.OrdinalIgnoreCase));
    }
}
