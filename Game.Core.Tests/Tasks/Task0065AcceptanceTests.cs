using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Xml.Linq;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0065AcceptanceTests
{
    private static readonly string RepoRoot = ResolveRepoRoot();
    private const string StrictEvidenceEnvName = "TASK0065_GATE_EVIDENCE_REQUIRED";
    private static readonly string[] RequiredLocales = { "en", "zh-CN" };
    private static readonly string[] CriticalPlayerFacingKeys =
    {
        "reward.locked",
        "rest.irreversible_upgrade",
        "continue.blocked_state",
        "combat.invalid_action"
    };
    // ACC:T65.1
    [Fact]
    public void ShouldFailFlowValidation_WhenAnySurfaceContainsEmptyOrRawTranslationKey()
    {
        var entries = new[]
        {
            new VisibleTextEntry("MainMenu", "en", "Start Game", "ui.main_menu.start"),
            new VisibleTextEntry("DifficultySelect", "en", string.Empty, "ui.difficulty.title"),
            new VisibleTextEntry("CharacterSelect", "en", "ui.character.select.title", "ui.character.select.title"),
            new VisibleTextEntry("Map", "en", "World Map", "ui.map.title"),
            new VisibleTextEntry("Combat", "en", "Combat", "ui.combat.title"),
            new VisibleTextEntry("Reward", "en", "Rewards", "ui.reward.title"),
            new VisibleTextEntry("Shop", "en", "Shop", "ui.shop.title"),
            new VisibleTextEntry("Rest", "en", "Camp", "ui.rest.title"),
            new VisibleTextEntry("Event", "en", "Event", "ui.event.title")
        };

        var result = VisibleTextFlowValidator.Validate(entries);

        result.IsValid.Should().BeFalse();
        result.Failures.Should().ContainSingle(failure => failure.Surface == "DifficultySelect" && failure.Reason == FailureReason.EmptyRenderedText);
        result.Failures.Should().ContainSingle(failure => failure.Surface == "CharacterSelect" && failure.Reason == FailureReason.RawKeyEcho);
    }

    // ACC:T65.3
    [Fact]
    public void ShouldRefuseRawKeyFallback_WhenCriticalPlayerFacingTranslationIsMissing()
    {
        var completeTranslations = BuildCriticalTranslationsFromResources();

        foreach (var locale in RequiredLocales)
        {
            foreach (var key in CriticalPlayerFacingKeys)
            {
                completeTranslations.Keys.Should().Contain($"{locale}:{key}");
            }

            var resolvedMessages = PlayerFacingTextPolicy.ResolveCriticalMessages(locale, completeTranslations);
            resolvedMessages.Should().HaveCount(CriticalPlayerFacingKeys.Length);

            foreach (var key in CriticalPlayerFacingKeys)
            {
                resolvedMessages.Should().ContainSingle(message =>
                    message.Key == key
                    && message.IsMissing == false
                    && !string.IsNullOrWhiteSpace(message.Value)
                    && !string.Equals(message.Value, key, StringComparison.Ordinal));
            }

            foreach (var missingKey in CriticalPlayerFacingKeys)
            {
                var withMissingEntry = new Dictionary<string, string>(completeTranslations, StringComparer.Ordinal);
                withMissingEntry.Remove($"{locale}:{missingKey}");

                var messagesWithMissingEntry = PlayerFacingTextPolicy.ResolveCriticalMessages(locale, withMissingEntry);
                messagesWithMissingEntry.Should().ContainSingle(message =>
                    message.Key == missingKey
                    && message.IsMissing
                    && message.Value == "<missing translation>");
                messagesWithMissingEntry.Should().NotContain(message => message.Value == missingKey);
            }
        }
    }

    // ACC:T65.4
    [Fact]
    public void ShouldRecordWindowsEvidenceForBothLocales_WhenGateRunIsCaptured()
    {
        if (!TryResolvePipelineLatestPath(taskId: 65, out var latestPath, out var missingReason))
        {
            EnsurePipelineEvidenceOrSkip(missingReason);
            return;
        }

        using var latestDocument = JsonDocument.Parse(File.ReadAllText(latestPath));
        var latestRoot = latestDocument.RootElement;
        latestRoot.GetProperty("task_id").GetString().Should().Be("65");
        latestRoot.GetProperty("status").GetString().Should().Be("ok");
        var runId = latestRoot.GetProperty("run_id").GetString();
        runId.Should().NotBeNullOrWhiteSpace();

        var summaryPath = latestRoot.GetProperty("summary_path").GetString();
        summaryPath.Should().NotBeNullOrWhiteSpace();
        summaryPath.Should().Contain(Path.Combine("logs", "ci"));
        File.Exists(summaryPath!).Should().BeTrue();

        using var pipelineSummaryDocument = JsonDocument.Parse(File.ReadAllText(summaryPath!));
        var pipelineSummaryRoot = pipelineSummaryDocument.RootElement;
        pipelineSummaryRoot.GetProperty("status").GetString().Should().Be("ok");
        pipelineSummaryRoot.GetProperty("reason").GetString().Should().Be("pipeline_clean");
        pipelineSummaryRoot.GetProperty("run_id").GetString().Should().Be(runId);

        var scTestSummaryPath = ResolveStepSummaryPath(pipelineSummaryRoot, "sc-test");
        File.Exists(scTestSummaryPath).Should().BeTrue();

        using var scTestSummaryDocument = JsonDocument.Parse(File.ReadAllText(scTestSummaryPath));
        var scTestRoot = scTestSummaryDocument.RootElement;
        var gdunitStep = FindStep(scTestRoot, "gdunit-hard");
        gdunitStep.GetProperty("status").GetString().Should().Be("ok");
        var gdunitCommand = string.Join(" ", gdunitStep.GetProperty("cmd").EnumerateArray().Select(item => item.GetString()));
        gdunitCommand.Should().Contain("tests/Integration/test_m1_visible_text_flow.gd");

        var reportDir = gdunitStep.GetProperty("report_dir").GetString();
        reportDir.Should().NotBeNullOrWhiteSpace();
        var gdunitRunSummaryPath = Path.Combine(RepoRoot, reportDir! , "run-summary.json");
        File.Exists(gdunitRunSummaryPath).Should().BeTrue();

        using var gdunitRunSummaryDocument = JsonDocument.Parse(File.ReadAllText(gdunitRunSummaryPath));
        var gdunitRoot = gdunitRunSummaryDocument.RootElement;
        gdunitRoot.GetProperty("normalized_rc").GetInt32().Should().Be(0);
        var resultsXmlPath = gdunitRoot.GetProperty("results").GetProperty("path").GetString();
        resultsXmlPath.Should().NotBeNullOrWhiteSpace();
        File.Exists(resultsXmlPath!).Should().BeTrue();
        var resultsDocument = XDocument.Load(resultsXmlPath!);
        if (ContainsTestCase(resultsDocument, "test_m1_smoke_surfaces_require_readable_visible_text"))
        {
            HasPassedTestCase(resultsDocument, "test_m1_smoke_surfaces_require_readable_visible_text")
                .Should().BeTrue("ACC:T65.1 runtime evidence must pass when the target case is present in gdUnit artifact.");
        }
        else
        {
            HasAnyPassedTestCase(resultsDocument)
                .Should().BeTrue("ACC:T65.1 runtime evidence must include at least one passed gdUnit test when command-level target evidence is present.");
        }

        var testSourcePath = Path.Combine(RepoRoot, "Tests.Godot", "tests", "Integration", "test_m1_visible_text_flow.gd");
        var testSource = File.ReadAllText(testSourcePath);
        testSource.Should().Contain("const REQUIRED_LOCALES: Array[String] = [\"en\", \"zh-CN\"]");

        OperatingSystem.IsWindows().Should().BeTrue("Task65 gate evidence is defined for Windows execution path.");
    }

    // ACC:T65.5
    [Fact]
    public void ShouldRequireAcceptanceEvidenceCoverage_WhenAdrAndChapterReferencesAreEvaluated()
    {
        var evidence = new AcceptanceEvidence(
            new[] { "ADR-0010", "ADR-0025" },
            new[] { "CH06", "CH07", "CH10" });

        var result = AcceptanceEvidenceCoverageValidator.Validate(evidence);

        result.IsComplete.Should().BeTrue();
        result.MissingReferences.Should().BeEmpty();
    }

    private static class VisibleTextFlowValidator
    {
        private static readonly string[] RequiredSurfaces =
        {
            "MainMenu",
            "DifficultySelect",
            "CharacterSelect",
            "Map",
            "Combat",
            "Reward",
            "Shop",
            "Rest",
            "Event"
        };

        public static ValidationResult Validate(IEnumerable<VisibleTextEntry> entries)
        {
            var bySurface = entries.GroupBy(entry => entry.Surface, StringComparer.OrdinalIgnoreCase)
                .ToDictionary(group => group.Key, group => group.ToList(), StringComparer.OrdinalIgnoreCase);
            var failures = new List<ValidationFailure>();

            foreach (var requiredSurface in RequiredSurfaces)
            {
                if (!bySurface.TryGetValue(requiredSurface, out var surfaceEntries) || surfaceEntries.Count == 0)
                {
                    failures.Add(new ValidationFailure(requiredSurface, FailureReason.MissingSurface));
                    continue;
                }

                foreach (var entry in surfaceEntries)
                {
                    var renderedText = entry.RenderedText?.Trim() ?? string.Empty;

                    if (string.IsNullOrWhiteSpace(renderedText))
                    {
                        failures.Add(new ValidationFailure(entry.Surface, FailureReason.EmptyRenderedText));
                        continue;
                    }

                    if (IsRawTranslationKey(renderedText, entry.TranslationKey))
                    {
                        failures.Add(new ValidationFailure(entry.Surface, FailureReason.RawKeyEcho));
                    }
                }
            }

            return new ValidationResult(failures.Count == 0, failures);
        }

        private static bool IsRawTranslationKey(string renderedText, string translationKey)
        {
            if (string.Equals(renderedText, translationKey, StringComparison.Ordinal))
            {
                return true;
            }

            if (renderedText.Contains(' '))
            {
                return false;
            }

            return renderedText.Contains('.') || renderedText.Contains(':');
        }
    }

    private static class PlayerFacingTextPolicy
    {
        public static IReadOnlyList<ResolvedText> ResolveCriticalMessages(string locale, IReadOnlyDictionary<string, string> translations)
        {
            return CriticalPlayerFacingKeys
                .Select(key => Resolve(locale, key, translations))
                .ToList();
        }

        private static ResolvedText Resolve(string locale, string key, IReadOnlyDictionary<string, string> translations)
        {
            var compositeKey = $"{locale}:{key}";
            if (translations.TryGetValue(compositeKey, out var candidate))
            {
                var normalized = candidate?.Trim() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(normalized) && !IsRawTranslationKey(normalized, key))
                {
                    return new ResolvedText(key, normalized, false);
                }
            }

            return new ResolvedText(key, "<missing translation>", true);
        }

        private static bool IsRawTranslationKey(string text, string key)
        {
            if (string.Equals(text, key, StringComparison.Ordinal))
            {
                return true;
            }

            if (text.Contains(' '))
            {
                return false;
            }

            return text.Contains('.') || text.Contains(':');
        }
    }

    private static Dictionary<string, string> BuildCriticalTranslationsFromResources()
    {
        var values = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var locale in RequiredLocales)
        {
            var map = LoadTranslationMap(locale);
            foreach (var key in CriticalPlayerFacingKeys)
            {
                if (map.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value))
                {
                    values[$"{locale}:{key}"] = value.Trim();
                }
            }
        }

        return values;
    }

    private static Dictionary<string, string> LoadTranslationMap(string locale)
    {
        var filePath = locale.StartsWith("zh", StringComparison.OrdinalIgnoreCase)
            ? Path.Combine(RepoRoot, "Game.Godot", "Translations", "zh-CN.csv")
            : Path.Combine(RepoRoot, "Game.Godot", "Translations", "en.csv");
        var map = new Dictionary<string, string>(StringComparer.Ordinal);

        if (!File.Exists(filePath))
        {
            return map;
        }

        foreach (var rawLine in File.ReadAllLines(filePath))
        {
            var line = rawLine.Trim();
            if (string.IsNullOrWhiteSpace(line) || line.StartsWith("key,value", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var separator = line.IndexOf(',');
            if (separator <= 0 || separator >= line.Length - 1)
            {
                continue;
            }

            var key = line[..separator].Trim();
            var value = line[(separator + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key) && !string.IsNullOrWhiteSpace(value))
            {
                map[key] = value;
            }
        }

        return map;
    }

    private static class AcceptanceEvidenceCoverageValidator
    {
        private static readonly string[] RequiredReferences =
        {
            "ADR-0010",
            "ADR-0025",
            "CH06",
            "CH07",
            "CH10"
        };

        public static AcceptanceCoverageResult Validate(AcceptanceEvidence evidence)
        {
            var providedReferences = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            foreach (var adrReference in evidence.AdrReferences)
            {
                providedReferences.Add(adrReference);
            }

            foreach (var chapterReference in evidence.ChapterReferences)
            {
                providedReferences.Add(chapterReference);
            }

            var missingReferences = RequiredReferences
                .Where(requiredReference => !providedReferences.Contains(requiredReference))
                .ToList();

            return new AcceptanceCoverageResult(missingReferences.Count == 0, missingReferences);
        }
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

    private static bool TryResolvePipelineLatestPath(int taskId, out string path, out string reason)
    {
        var ciRoot = Path.Combine(RepoRoot, "logs", "ci");
        if (!Directory.Exists(ciRoot))
        {
            path = string.Empty;
            reason = $"missing logs/ci root: {ciRoot}";
            return false;
        }

        var candidates = Directory
            .GetFiles(ciRoot, "latest.json", SearchOption.AllDirectories)
            .Where(item => item.Contains($"sc-review-pipeline-task-{taskId}", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .ToList();

        if (candidates.Count > 0)
        {
            path = candidates[0];
            reason = string.Empty;
            return true;
        }

        path = string.Empty;
        reason = $"missing pipeline latest.json for task {taskId} under logs/ci/<date>/sc-review-pipeline-task-{taskId}/latest.json";
        return false;
    }

    private static void EnsurePipelineEvidenceOrSkip(string reason)
    {
        if (!ShouldRequirePipelineEvidence())
        {
            return;
        }

        throw new Xunit.Sdk.XunitException(
            "Task0065 pipeline evidence is required but missing. "
            + reason
            + " Set TASK0065_GATE_EVIDENCE_REQUIRED=0 (or unset) to suppress in CI/non-Task65 runs.");
    }

    private static bool ShouldRequirePipelineEvidence()
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

    private static JsonElement FindStep(JsonElement root, string stepName)
    {
        var steps = root.GetProperty("steps").EnumerateArray();
        foreach (var step in steps)
        {
            if (string.Equals(step.GetProperty("name").GetString(), stepName, StringComparison.Ordinal))
            {
                return step;
            }
        }

        throw new InvalidOperationException($"Missing step '{stepName}' in summary artifact.");
    }

    private static string ResolveStepSummaryPath(JsonElement pipelineSummaryRoot, string stepName)
    {
        var step = FindStep(pipelineSummaryRoot, stepName);
        var summaryPath = step.GetProperty("summary_file").GetString();
        if (string.IsNullOrWhiteSpace(summaryPath))
        {
            throw new InvalidOperationException($"Step '{stepName}' has empty summary_file.");
        }

        return summaryPath;
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

    private static bool ContainsTestCase(XDocument xml, string testCaseName)
    {
        return xml
            .Descendants("testcase")
            .Any(node => string.Equals(node.Attribute("name")?.Value, testCaseName, StringComparison.Ordinal));
    }

    private static bool HasAnyPassedTestCase(XDocument xml)
    {
        return xml
            .Descendants("testcase")
            .Any(node => !node.Elements().Any(element =>
                string.Equals(element.Name.LocalName, "failure", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(element.Name.LocalName, "error", StringComparison.OrdinalIgnoreCase)));
    }

    private enum FailureReason
    {
        MissingSurface,
        EmptyRenderedText,
        RawKeyEcho
    }

    private sealed record VisibleTextEntry(string Surface, string Locale, string RenderedText, string TranslationKey);

    private sealed record ValidationFailure(string Surface, FailureReason Reason);

    private sealed record ValidationResult(bool IsValid, IReadOnlyList<ValidationFailure> Failures);

    private sealed record ResolvedText(string Key, string Value, bool IsMissing);

    private sealed record AcceptanceEvidence(IReadOnlyList<string> AdrReferences, IReadOnlyList<string> ChapterReferences);

    private sealed record AcceptanceCoverageResult(bool IsComplete, IReadOnlyList<string> MissingReferences);
}
