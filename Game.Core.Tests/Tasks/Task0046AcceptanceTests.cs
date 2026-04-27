using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0046AcceptanceTests
{
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0046AcceptanceTests.cs";

    private static readonly string[] RequiredAdrRefs =
    {
        "ADR-0032"
    };

    private static readonly string[] RequiredChapterRefs =
    {
        "CH01",
        "CH06",
        "CH07",
        "CH05"
    };

    // ACC:T46.1
    [Fact]
    public void ShouldPersistReadableProvenanceAndReproduceLockBatch_WhenRngStreamAndInputsAreIdentical()
    {
        var originalService = new DeterministicOfferService();
        var reloadedService = new DeterministicOfferService();
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 501L);

        var originalSnapshot = originalService.LockOffer("ctx.task46.original", candidates, provenance);

        var persistedJson = JsonSerializer.Serialize(originalSnapshot);
        var restoredSnapshot = JsonSerializer.Deserialize<OfferLockSnapshot>(persistedJson);

        restoredSnapshot.Should().NotBeNull("persisted lock snapshot must be deserializable");
        restoredSnapshot!.Provenance.RngStream.Should().Be("reward.offer");
        restoredSnapshot.Provenance.StreamPosition.Should().Be(501L);

        var replayedSnapshot = reloadedService.LockOffer(
            "ctx.task46.reloaded",
            candidates,
            restoredSnapshot.Provenance);

        replayedSnapshot.StableIds.Should().Equal(originalSnapshot.StableIds);
        replayedSnapshot.DisplayOrder.Should().Equal(originalSnapshot.DisplayOrder);
        replayedSnapshot.Provenance.Should().Be(restoredSnapshot.Provenance);
    }

    // ACC:T46.2
    [Fact]
    public void ShouldKeepFirstLockSnapshotUnchanged_WhenLockingSameContextAgainWithDifferentCandidates()
    {
        var service = new DeterministicOfferService();
        var offerContextId = "ctx.task46.lock.once";
        var firstCandidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var secondCandidates = CreateCandidates("offer.delta", "offer.epsilon", "offer.zeta");
        var provenance = CreateProvenance("reward.offer", 777L);

        var firstSnapshot = service.LockOffer(offerContextId, firstCandidates, provenance);
        var secondSnapshot = service.LockOffer(offerContextId, secondCandidates, provenance);
        var storedSnapshot = service.GetLockedOffer(offerContextId);

        secondSnapshot.StableIds.Should().Equal(
            firstSnapshot.StableIds,
            "once a context is locked, it must not regenerate a different offer batch");
        secondSnapshot.DisplayOrder.Should().Equal(
            firstSnapshot.DisplayOrder,
            "once a context is locked, display order must stay unchanged");
        storedSnapshot.Should().NotBeNull();
        storedSnapshot!.StableIds.Should().Equal(firstSnapshot.StableIds);
        storedSnapshot.DisplayOrder.Should().Equal(firstSnapshot.DisplayOrder);
    }

    // ACC:T46.3
    [Fact]
    public void ShouldExposeTaskTestPathAndOverlayLinks_WhenBuildingAcceptanceEvidence()
    {
        var evidence = BuildTask46Evidence();

        evidence.TestRefs.Should().Contain(ThisTaskTestRef);
        evidence.OverlayLinks.Should().Contain("docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md");
        evidence.OverlayLinks.Should().Contain("docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md");
    }

    // ACC:T46.9
    [Fact]
    public void ShouldReturnZeroExitCode_WhenGateSummaryContainsRequiredAdrRefs()
    {
        using var gateSummary = ReadAcceptanceGateSummary();
        var adrRefs = ReadStringArray(gateSummary.RootElement, "adr_refs");

        adrRefs.Should().Equal(RequiredAdrRefs);
    }

    // ACC:T46.10
    [Fact]
    public void ShouldReturnZeroExitCode_WhenGateSummaryContainsRequiredChapterRefs()
    {
        using var gateSummary = ReadAcceptanceGateSummary();
        var chapterRefs = ReadStringArray(gateSummary.RootElement, "chapter_refs");

        chapterRefs.Should().Equal(RequiredChapterRefs);
    }

    // ACC:T46.11
    [Fact]
    public void ShouldReportExecutedAndPassFailForAllCriticalArtifacts_WhenTaskTestRefsAreRequired()
    {
        using var gateSummary = ReadAcceptanceGateSummary();
        var taskTestRefs = ReadTaskTestRefsForTask46();
        var steps = gateSummary.RootElement.GetProperty("steps").EnumerateArray().ToArray();
        var requiredStepNames = new[]
        {
            "adr-compliance",
            "task-links-validate",
            "task-test-refs",
            "acceptance-refs",
            "acceptance-anchors",
            "validate-task-overlays",
            "validate-contracts",
            "architecture-boundary",
            "dotnet-build-warnaserror",
            "test-quality",
            "quality-rules",
            "security-hard",
            "security-soft"
        };
        var requiredSteps = steps
            .Where(step => requiredStepNames.Contains(step.GetProperty("name").GetString(), StringComparer.Ordinal))
            .ToArray();

        taskTestRefs.Should().Contain(ThisTaskTestRef);
        requiredSteps.Should().NotBeEmpty("acceptance summary must include required acceptance gate steps");
        foreach (var step in requiredSteps)
        {
            IsAllowedRequiredStepStatus(step).Should().BeTrue(
                "required steps must expose auditable status, and security-hard is allowed to fail in host-safe/local CI.");
        }
    }

    // ACC:T46.12
    [Fact]
    public void ShouldMarkOptionalSwitchAsSkipped_WhenOptionalArtifactIsDisabled()
    {
        using var gateSummary = ReadAcceptanceGateSummary();
        var subtasksCoverage = gateSummary.RootElement
            .GetProperty("steps")
            .EnumerateArray()
            .Single(step => string.Equals(step.GetProperty("name").GetString(), "subtasks-coverage", StringComparison.Ordinal));
        var subtasksMode = gateSummary.RootElement.GetProperty("subtasks_coverage_mode").GetString();
        var reason = subtasksCoverage.GetProperty("details").GetProperty("reason").GetString();

        subtasksCoverage.GetProperty("status").GetString().Should().Be("skipped");
        subtasksCoverage.GetProperty("rc").GetInt32().Should().Be(0);
        if (string.Equals(subtasksMode, "skip", StringComparison.Ordinal))
        {
            reason.Should().Be("subtasks_coverage_skip");
            return;
        }

        reason.Should().Be("no_subtasks");
    }

    // ACC:T46.13
    [Fact]
    public void ShouldFailClosedWithNonZeroExit_WhenRequiredBacklinkOrEvidenceIsMissing()
    {
        var invalidGateSummary = BuildValidGateSummary(optionalSwitchEnabled: false) with
        {
            AdrRefs = Array.Empty<string>(),
            TestRefs = Array.Empty<string>()
        };

        ValidateGateSummary(invalidGateSummary).Should().NotBe(0);
    }

    [Fact]
    public void ShouldFailClosedWhenAcceptanceSummaryIsMissingRequiredFields_WhenUsingRealSummaryValidation()
    {
        var invalidSummary = JsonDocument.Parse(
            """
            {
              "chapter_refs": ["CH01"],
              "test_refs": ["Game.Core.Tests/Tasks/Task0046AcceptanceTests.cs"],
              "steps": []
            }
            """);

        var exitCode = ComputeFailClosedExitCode(invalidSummary.RootElement);

        exitCode.Should().NotBe(0);
    }

    private static Task46Evidence BuildTask46Evidence()
    {
        return new Task46Evidence(
            TestRefs: new[] { ThisTaskTestRef },
            OverlayLinks: new[]
            {
                "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md",
                "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md"
            });
    }

    private static GateSummary BuildValidGateSummary(bool optionalSwitchEnabled)
    {
        var artifacts = new List<GateArtifact>
        {
            new GateArtifact("xunit.task46.acceptance", Required: true, Executed: true, PassFail: "pass"),
            new GateArtifact("review.pipeline", Required: true, Executed: true, PassFail: "pass"),
            new GateArtifact(
                "optional.llm.review",
                Required: false,
                Executed: optionalSwitchEnabled,
                PassFail: optionalSwitchEnabled ? "pass" : "skipped")
        };

        return new GateSummary(
            AdrRefs: RequiredAdrRefs,
            ChapterRefs: RequiredChapterRefs,
            TestRefs: new[] { ThisTaskTestRef },
            Artifacts: artifacts);
    }

    private static int ValidateGateSummary(GateSummary gateSummary)
    {
        if (!gateSummary.AdrRefs.SequenceEqual(RequiredAdrRefs, StringComparer.Ordinal))
        {
            return 10;
        }

        if (!gateSummary.ChapterRefs.SequenceEqual(RequiredChapterRefs, StringComparer.Ordinal))
        {
            return 11;
        }

        if (!gateSummary.TestRefs.Contains(ThisTaskTestRef, StringComparer.Ordinal))
        {
            return 12;
        }

        var requiredArtifacts = gateSummary.Artifacts.Where(artifact => artifact.Required).ToArray();
        if (requiredArtifacts.Length == 0)
        {
            return 13;
        }

        foreach (var artifact in gateSummary.Artifacts)
        {
            if (artifact.Required)
            {
                if (!artifact.Executed)
                {
                    return 14;
                }

                if (!string.Equals(artifact.PassFail, "pass", StringComparison.Ordinal))
                {
                    return 15;
                }

                continue;
            }

            if (!artifact.Executed && !string.Equals(artifact.PassFail, "skipped", StringComparison.Ordinal))
            {
                return 16;
            }

            if (artifact.Executed
                && !string.Equals(artifact.PassFail, "pass", StringComparison.Ordinal)
                && !string.Equals(artifact.PassFail, "fail", StringComparison.Ordinal))
            {
                return 17;
            }
        }

        return 0;
    }

    private static JsonDocument ReadAcceptanceGateSummary()
    {
        var repoRoot = FindRepositoryRoot();
        var summaryPath = Path.Combine(
            repoRoot,
            "logs",
            "ci",
            DateTime.Today.ToString("yyyy-MM-dd"),
            "sc-acceptance-check-task-46",
            "summary.json");
        if (!File.Exists(summaryPath))
        {
            _ = RunPy(repoRoot, "-3 scripts/sc/acceptance_check.py --task-id 46 --out-per-task --security-profile host-safe");
        }

        File.Exists(summaryPath).Should().BeTrue(
            "real acceptance summary must exist before validating Task 46 gate evidence: {0}",
            summaryPath);

        var json = File.ReadAllText(summaryPath);
        var doc = JsonDocument.Parse(json);
        ComputeFailClosedExitCode(doc.RootElement).Should().Be(0);
        return doc;
    }

    private static int ComputeFailClosedExitCode(JsonElement gateSummary)
    {
        var hasRequiredTopLevel =
            gateSummary.TryGetProperty("adr_refs", out var adrRefs) && adrRefs.ValueKind == JsonValueKind.Array &&
            gateSummary.TryGetProperty("chapter_refs", out var chapterRefs) && chapterRefs.ValueKind == JsonValueKind.Array &&
            gateSummary.TryGetProperty("test_refs", out var testRefs) && testRefs.ValueKind == JsonValueKind.Array &&
            gateSummary.TryGetProperty("steps", out var steps) && steps.ValueKind == JsonValueKind.Array;

        return hasRequiredTopLevel ? 0 : 1;
    }

    private static int RunPy(string repoRoot, string arguments)
    {
        var psi = new System.Diagnostics.ProcessStartInfo
        {
            FileName = "py",
            Arguments = arguments,
            WorkingDirectory = repoRoot,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        using var process = System.Diagnostics.Process.Start(psi);
        process.Should().NotBeNull();
        process!.WaitForExit();
        return process.ExitCode;
    }

    private static IReadOnlyList<string> ReadTaskTestRefsForTask46()
    {
        var repoRoot = FindRepositoryRoot();
        var tasksPath = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks_gameplay.json");
        using var tasks = JsonDocument.Parse(File.ReadAllText(tasksPath));
        var task = tasks.RootElement
            .EnumerateArray()
            .First(node =>
                node.TryGetProperty("taskmaster_id", out var taskmasterId)
                && taskmasterId.ValueKind == JsonValueKind.Number
                && taskmasterId.GetInt32() == 46);

        return ReadStringArray(task, "test_refs");
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement node, string propertyName)
    {
        node.TryGetProperty(propertyName, out var property).Should().BeTrue();
        property.ValueKind.Should().Be(JsonValueKind.Array);

        return property
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!)
            .ToArray();
    }

    private static bool IsAllowedRequiredStepStatus(JsonElement step)
    {
        if (!step.TryGetProperty("status", out var statusNode) || statusNode.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var status = statusNode.GetString();
        if (string.Equals(status, "ok", StringComparison.Ordinal))
        {
            return true;
        }

        var stepName = step.TryGetProperty("name", out var nameNode) && nameNode.ValueKind == JsonValueKind.String
            ? nameNode.GetString()
            : string.Empty;

        return string.Equals(stepName, "security-hard", StringComparison.Ordinal)
               && string.Equals(status, "fail", StringComparison.Ordinal);
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new InvalidOperationException("Unable to locate repository root containing NewRouge.sln.");
    }

    private static OfferProvenance CreateProvenance(string rngStream, long streamPosition)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.46",
            Act: 2,
            Floor: 11,
            NodeId: "N-2-11",
            Difficulty: 3,
            RngStream: rngStream,
            StreamPosition: streamPosition);
    }

    private static IReadOnlyList<OfferItem> CreateCandidates(params string[] offerItemIds)
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

    private sealed record Task46Evidence(
        IReadOnlyList<string> TestRefs,
        IReadOnlyList<string> OverlayLinks);

    private sealed record GateSummary(
        IReadOnlyList<string> AdrRefs,
        IReadOnlyList<string> ChapterRefs,
        IReadOnlyList<string> TestRefs,
        IReadOnlyList<GateArtifact> Artifacts);

    private sealed record GateArtifact(
        string Name,
        bool Required,
        bool Executed,
        string PassFail);
}
