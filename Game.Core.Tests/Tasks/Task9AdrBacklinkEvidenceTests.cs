using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task9AdrBacklinkEvidenceTests
{
    private const string StrictEvidenceEnvName = "TASK0009_ADR_BACKLINK_EVIDENCE_REQUIRED";
    private static readonly string[] RequiredAdrIds = { "ADR-0032", "ADR-0021" };
    private const string OverlayChecklistPath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";

    // ACC:T9.11
    [Fact]
    public void ShouldAcceptChecklist_WhenRequiredAdrBackLinksIncludeAuditableEvidencePaths()
    {
        var checklistText = string.Join(
            Environment.NewLine,
            "- ADR-0032 back-link check: pass. Evidence: logs/ci/evidence/task-0009-adr-0032-backlink.json",
            "- ADR-0021 back-link check: pass. Evidence: logs/ci/evidence/task-0009-adr-0021-backlink.json");

        var result = EvaluateChecklist(checklistText, requireEvidenceFileExists: false);

        result.IsAccepted.Should().BeTrue(
            "acceptance requires ADR-0032 and ADR-0021 with auditable evidence paths");
        result.Failures.Should().BeEmpty();
    }

    [Fact]
    public void ShouldRejectChecklist_WhenAdr0021BackLinkIsMissing()
    {
        var checklistText = "- ADR-0032 back-link check: pass. Evidence: logs/ci/evidence/task-0009-adr-0032-backlink.json";

        var result = EvaluateChecklist(checklistText, requireEvidenceFileExists: false);

        result.IsAccepted.Should().BeFalse();
        result.Failures.Should().Contain("Missing required ADR back-link: ADR-0021");
    }

    [Fact]
    public void ShouldRejectChecklist_WhenEvidencePathIsMissingForRequiredAdrBackLink()
    {
        var checklistText = string.Join(
            Environment.NewLine,
            "- ADR-0032 back-link check: pass.",
            "- ADR-0021 back-link check: pass. Evidence: logs/ci/evidence/task-0009-adr-0021-backlink.json");

        var result = EvaluateChecklist(checklistText, requireEvidenceFileExists: false);

        result.IsAccepted.Should().BeFalse();
        result.Failures.Should().Contain("Missing auditable evidence path for ADR-0032");
    }

    [Fact]
    public void ShouldRejectChecklist_WhenEvidenceFileDoesNotExist()
    {
        var checklistText = string.Join(
            Environment.NewLine,
            "- ADR-0032 back-link check: pass. Evidence: logs/ci/evidence/not-found-0032.json",
            "- ADR-0021 back-link check: pass. Evidence: logs/ci/evidence/not-found-0021.json");

        var result = EvaluateChecklist(checklistText);

        result.IsAccepted.Should().BeFalse();
        result.Failures.Should().Contain(item => item.Contains("must exist on disk", StringComparison.Ordinal));
    }

    [Fact]
    public void ShouldContainRequiredAdrMentions_WhenReadingOverlayAcceptanceChecklist()
    {
        var checklistPath = Path.Combine(FindRepoRoot(), OverlayChecklistPath.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(checklistPath) && !ShouldRequireOverlayChecklist())
        {
            return;
        }
        File.Exists(checklistPath).Should().BeTrue("task acceptance evidence must include the overlay checklist file");

        var checklistText = File.ReadAllText(checklistPath);
        var result = EvaluateChecklist(
            checklistText,
            requireEvidenceFileExists: ShouldRequireOverlayChecklist());
        result.IsAccepted.Should().BeTrue(
            "overlay checklist must include ADR-0032 and ADR-0021 with auditable logs/ evidence paths");
        result.Failures.Should().BeEmpty();
    }

    private static bool ShouldRequireOverlayChecklist()
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

    private static AdrChecklistEvaluation EvaluateChecklist(string checklistText, bool requireEvidenceFileExists = true)
    {
        var failures = new List<string>();
        var lines = checklistText
            .Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(line => line.Trim())
            .ToArray();

        foreach (var adrId in RequiredAdrIds)
        {
            var matchingLine = lines.FirstOrDefault(line =>
                line.Contains(adrId, StringComparison.OrdinalIgnoreCase)
                && line.Contains("back-link", StringComparison.OrdinalIgnoreCase));
            if (matchingLine is null)
            {
                failures.Add($"Missing required ADR back-link: {adrId}");
                continue;
            }

            var evidencePath = ExtractEvidencePath(matchingLine);
            if (string.IsNullOrWhiteSpace(evidencePath))
            {
                failures.Add($"Missing auditable evidence path for {adrId}");
                continue;
            }

            if (!evidencePath.StartsWith("logs/", StringComparison.Ordinal))
            {
                failures.Add($"Evidence path for {adrId} must be repository-relative under logs/: {evidencePath}");
                continue;
            }

            var absolutePath = Path.Combine(FindRepoRoot(), evidencePath.Replace('/', Path.DirectorySeparatorChar));
            if (requireEvidenceFileExists && !File.Exists(absolutePath))
            {
                failures.Add($"Evidence path for {adrId} must exist on disk: {evidencePath}");
            }

        }

        return new AdrChecklistEvaluation(failures.Count == 0, failures);
    }

    private static string? ExtractEvidencePath(string line)
    {
        var match = Regex.Match(
            line,
            @"Evidence:\s*(?<path>[^,\s]+)",
            RegexOptions.CultureInvariant | RegexOptions.IgnoreCase);

        return match.Success ? match.Groups["path"].Value : null;
    }

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln"))
                || File.Exists(Path.Combine(current.FullName, "AGENTS.md")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new InvalidOperationException("Unable to locate repository root.");
    }

    private sealed class AdrChecklistEvaluation
    {
        public AdrChecklistEvaluation(bool isAccepted, IReadOnlyCollection<string> failures)
        {
            IsAccepted = isAccepted;
            Failures = failures;
        }

        public bool IsAccepted { get; }

        public IReadOnlyCollection<string> Failures { get; }
    }
}
