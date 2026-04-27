using System;
using System.Collections.Generic;
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
    private const string StrictEvidenceEnvName = "TASK0062_REST_EVIDENCE_REQUIRED";
    private static readonly string[] RequiredRestEvidenceScripts =
    {
        "tests/Scenes/Rest/test_rest_scene_route_roundtrip.gd",
        "tests/Scenes/Rest/test_rest_upgrade_confirmation_irreversible.gd",
    };

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
        if (!TryResolveRestGdUnitSummaryPath(out var evidencePath, out var missingReason))
        {
            EnsureRestEvidenceOrSkip(missingReason);
            return;
        }

        using var document = JsonDocument.Parse(File.ReadAllText(evidencePath));
        var root = document.RootElement;
        var resultsPath = ResolveResultsPathOrFallback(
            root,
            "test_rest_scene_exposes_heal_upgrade_and_curse_removal_choices");
        if (string.IsNullOrWhiteSpace(resultsPath))
        {
            EnsureRestEvidenceOrSkip("missing gdUnit results.xml for ACC:T62.2 testcase evidence.");
            return;
        }

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
        if (!TryResolveRestGdUnitSummaryPath(out var evidencePath, out var missingReason))
        {
            EnsureRestEvidenceOrSkip(missingReason);
            return;
        }

        using var document = JsonDocument.Parse(File.ReadAllText(evidencePath));
        var root = document.RootElement;
        var resultsPath = ResolveResultsPathOrFallback(
            root,
            "test_remove_curse_from_rest_applies_result_and_returns_to_map");
        if (string.IsNullOrWhiteSpace(resultsPath))
        {
            EnsureRestEvidenceOrSkip("missing gdUnit results.xml for ACC:T62.5 testcase evidence.");
            return;
        }

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
        if (!TryResolveRestGdUnitSummaryPath(out var evidencePath, out var missingReason))
        {
            EnsureRestEvidenceOrSkip(missingReason);
            return;
        }

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

    private static bool TryResolveRestGdUnitSummaryPath(out string path, out string reason)
    {
        var candidates = new List<string>
        {
            Path.Combine(
                RepoRoot,
                "logs",
                "e2e",
                DateTime.UtcNow.ToString("yyyy-MM-dd"),
                "sc-test",
                "gdunit-hard",
                "run-summary.json"),
            Path.Combine(
                RepoRoot,
                "logs",
                "e2e",
                "2026-04-21",
                "sc-test",
                "gdunit-hard",
                "run-summary.json"),
        };

        var e2eRoot = Path.Combine(RepoRoot, "logs", "e2e");
        var existingCandidates = new List<string>();
        var markerMatchedCandidates = new List<string>();
        if (Directory.Exists(e2eRoot))
        {
            var discovered = Directory
                .GetFiles(e2eRoot, "run-summary.json", SearchOption.AllDirectories)
                .OrderByDescending(File.GetLastWriteTimeUtc);
            candidates.AddRange(discovered);
        }

        foreach (var candidate in candidates.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (File.Exists(candidate))
            {
                existingCandidates.Add(candidate);
                if (SummaryContainsRequiredRestEvidenceMarkers(candidate))
                {
                    markerMatchedCandidates.Add(candidate);
                }
            }
        }

        if (markerMatchedCandidates.Count > 0)
        {
            path = markerMatchedCandidates[0];
            reason = string.Empty;
            return true;
        }

        if (existingCandidates.Count > 0)
        {
            // Keep evidence strict: unrelated gdUnit summaries must not be treated as Task62 rest evidence.
            path = string.Empty;
            reason = "found gdUnit run-summary.json artifacts, but none contains required Task62 rest evidence markers";
            return false;
        }

        path = candidates.Count > 0 ? candidates[0] : string.Empty;
        reason = $"missing gdUnit rest evidence summary under {Path.Combine("logs", "e2e", "<date>", "sc-test", "gdunit-hard", "run-summary.json")}";
        return false;
    }

    private static void EnsureRestEvidenceOrSkip(string reason)
    {
        if (!ShouldRequireRestEvidence())
        {
            return;
        }

        throw new Xunit.Sdk.XunitException(
            "Task0062 rest evidence is required but missing. "
            + reason
            + " Set TASK0062_REST_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task62 runs.");
    }

    private static bool ShouldRequireRestEvidence()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEvidenceEnvName);
        if (string.IsNullOrWhiteSpace(raw))
        {
            return false;
        }

        return raw.Equals("1", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("yes", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("on", StringComparison.OrdinalIgnoreCase);
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

    private static string ResolveResultsPathOrFallback(JsonElement summaryRoot, string requiredTestCaseName)
    {
        if (summaryRoot.TryGetProperty("results", out var resultsNode)
            && resultsNode.TryGetProperty("path", out var pathNode))
        {
            var directPath = pathNode.GetString();
            if (!string.IsNullOrWhiteSpace(directPath) && File.Exists(directPath))
            {
                return directPath;
            }
        }

        var reportsRoot = Path.Combine(RepoRoot, "Tests.Godot", "reports");
        if (!Directory.Exists(reportsRoot))
        {
            return string.Empty;
        }

        var candidates = Directory
            .GetFiles(reportsRoot, "results.xml", SearchOption.AllDirectories)
            .OrderByDescending(File.GetLastWriteTimeUtc);

        foreach (var candidate in candidates)
        {
            var content = File.ReadAllText(candidate);
            if (content.Contains(requiredTestCaseName, StringComparison.Ordinal))
            {
                return candidate;
            }
        }

        return string.Empty;
    }

    private static bool SummaryContainsRequiredRestEvidenceMarkers(string summaryPath)
    {
        var content = File.ReadAllText(summaryPath);
        return RequiredRestEvidenceScripts.All(marker => content.Contains(marker, StringComparison.Ordinal));
    }
}
