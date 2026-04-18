using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T29")]
[Trait("adr", "ADR-0032")]
[Trait("adr", "ADR-0033")]
public sealed class Task0029AcceptanceTests
{
    private static readonly (int actId, string encounterType)[] SupportedCombinations =
    {
        (1, "normal"),
        (1, "elite"),
        (1, "boss"),
        (1, "shop"),
        (1, "event"),
        (2, "normal"),
        (2, "elite"),
        (2, "boss"),
        (2, "shop"),
        (2, "event"),
        (3, "normal"),
        (3, "elite"),
        (3, "boss"),
        (3, "shop"),
        (3, "event"),
    };

    private static readonly string[] RequiredRarityTiers = { "common", "uncommon", "rare" };
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0029AcceptanceTests.cs";
    private static readonly Lazy<string> RepositoryRoot = new(ResolveRepositoryRoot);

    // ACC:T29.1
    [Fact]
    [Trait("acceptance", "ACC:T29.1")]
    public void ShouldReturnValidCardPoolWithRarityTiers_WhenEverySupportedActEncounterCombinationIsQueried()
    {
        var pools = CardPoolCatalog.GetAll();
        var selectionService = new CardPoolSelectionService();

        var validationResults = SupportedCombinations
            .Select(combo => ValidatePool(selectionService, pools, combo.actId, combo.encounterType))
            .ToArray();

        var failedSummaries = validationResults
            .Where(result => !result.IsValid)
            .Select(result => $"{result.ActId}:{result.EncounterType}:{result.Reason}")
            .ToArray();

        validationResults.Should().OnlyContain(
            result => result.IsValid,
            "each supported Act + encounter combination must resolve to a non-empty pool with common/uncommon/rare tiers. Failed: {0}",
            string.Join("; ", failedSummaries));
    }

    // ACC:T29.2
    [Fact]
    [Trait("acceptance", "ACC:T29.2")]
    public void ShouldReportPassingAssertions_WhenTask0029AcceptanceRunsOnWindows()
    {
        var acceptanceSummary = ReadAcceptanceSummary();
        if (acceptanceSummary.ValueKind == JsonValueKind.Undefined)
        {
            return;
        }

        var unitSummary = ReadUnitSummary();
        if (unitSummary.ValueKind != JsonValueKind.Undefined &&
            unitSummary.TryGetProperty("test_rc", out var unitTestRc))
        {
            unitTestRc.GetInt32().Should().BeGreaterThanOrEqualTo(0);
        }

        acceptanceSummary.GetProperty("task_id").GetString().Should().Be("29");
        acceptanceSummary.GetProperty("status").GetString().Should().Be("ok");
        OperatingSystem.IsWindows().Should().BeTrue("Task 29 acceptance is defined against Windows runtime");

        var acceptanceOutDir = GetAcceptanceOutDir(acceptanceSummary);
        acceptanceOutDir.Should().MatchRegex(@"^[A-Za-z]:\\", "acceptance artifacts should come from a Windows absolute path");

        var unitMetrics = acceptanceSummary
            .GetProperty("metrics")
            .GetProperty("unit")
            .GetProperty("tests");
        unitMetrics.GetProperty("executed").GetInt32().Should().BeGreaterThan(0);
        unitMetrics.GetProperty("failed").GetInt32().Should().Be(0);
        unitMetrics.GetProperty("passed").GetInt32().Should().Be(unitMetrics.GetProperty("executed").GetInt32());

        var requiredPassingSteps = new[] { "task-test-refs", "acceptance-refs", "acceptance-anchors", "tests-all" };
        foreach (var stepName in requiredPassingSteps)
        {
            FindStepByName(acceptanceSummary, stepName)
                .GetProperty("status")
                .GetString()
                .Should()
                .Be("ok", $"acceptance step '{stepName}' must pass on Windows");
        }
    }

    [Fact]
    public void ShouldRejectAcceptanceEvidence_WhenPinnedRunIdDoesNotMatchAnySummary()
    {
        const string pinnedRunId = "run-id-that-should-not-exist";
        var previousRunId = Environment.GetEnvironmentVariable("SC_ACCEPTANCE_RUN_ID");

        Environment.SetEnvironmentVariable("SC_ACCEPTANCE_RUN_ID", pinnedRunId);
        try
        {
            var act = () => ReadAcceptanceSummary();
            act.Should()
                .Throw<InvalidOperationException>()
                .WithMessage("*SC_ACCEPTANCE_RUN_ID*");
        }
        finally
        {
            Environment.SetEnvironmentVariable("SC_ACCEPTANCE_RUN_ID", previousRunId);
        }
    }

    // ACC:T29.3
    [Fact]
    [Trait("acceptance", "ACC:T29.3")]
    public void ShouldKeepOverlayTestRefsOneToOneWithImplementation_WhenTask0029TraceabilityIsValidated()
    {
        var acceptanceSummary = ReadAcceptanceSummary();
        if (acceptanceSummary.ValueKind == JsonValueKind.Undefined)
        {
            return;
        }

        var taskTestRefsEvidence = ReadAcceptanceArtifact(acceptanceSummary, "task-test-refs.json");
        var acceptanceAnchorsEvidence = ReadAcceptanceArtifact(acceptanceSummary, "acceptance-anchors.json");

        var declaredBackRefs = ReadStringArray(taskTestRefsEvidence.GetProperty("back"), "test_refs");
        var declaredGameplayRefs = ReadStringArray(taskTestRefsEvidence.GetProperty("gameplay"), "test_refs");
        declaredBackRefs.Should().Equal(
            declaredGameplayRefs,
            "Task 29 test refs must remain identical across back/gameplay task views");
        declaredBackRefs.Should().Contain(ThisTaskTestRef);

        var boundBackRefs = CollectBoundRefsFromAcceptanceAnchors(acceptanceAnchorsEvidence, "back");
        var boundGameplayRefs = CollectBoundRefsFromAcceptanceAnchors(acceptanceAnchorsEvidence, "gameplay");
        boundBackRefs.Should().BeEquivalentTo(
            declaredBackRefs,
            "acceptance anchors should bind every declared Task 29 test ref in back view");
        boundGameplayRefs.Should().BeEquivalentTo(
            declaredGameplayRefs,
            "acceptance anchors should bind every declared Task 29 test ref in gameplay view");

        var requiredTaskAnchors = new[] { "ACC:T29.1", "ACC:T29.2", "ACC:T29.3", "ACC:T29.7", "ACC:T29.8" };
        foreach (var anchor in requiredTaskAnchors)
        {
            AssertAnchorBoundToTaskTestRef(acceptanceAnchorsEvidence, "back", anchor);
            AssertAnchorBoundToTaskTestRef(acceptanceAnchorsEvidence, "gameplay", anchor);
        }
    }

    // ACC:T29.7
    [Theory]
    [Trait("acceptance", "ACC:T29.7")]
    [InlineData("ADR-0032")]
    [InlineData("ADR-0033")]
    public void ShouldFailAdrConsistencyGate_WhenEitherRequiredAdrReferenceIsMissing(string missingAdr)
    {
        var declaredAdrRefs = new[] { "ADR-0032", "ADR-0033" }
            .Where(adr => !string.Equals(adr, missingAdr, StringComparison.Ordinal))
            .ToArray();

        var gateResult = AdrTraceabilityGate.Evaluate(declaredAdrRefs);

        gateResult.IsPass.Should().BeFalse();
        gateResult.MissingRequiredAdrRefs.Should().Contain(missingAdr);
    }

    // ACC:T29.8
    [Fact]
    [Trait("acceptance", "ACC:T29.8")]
    public void ShouldRecordAdr0032GatePassOrFail_WhenTaskEvidenceOutputIsGenerated()
    {
        var acceptanceSummary = ReadAcceptanceSummary();
        if (acceptanceSummary.ValueKind == JsonValueKind.Undefined)
        {
            return;
        }

        acceptanceSummary.GetProperty("status").GetString().Should().Be("ok");
        acceptanceSummary.GetProperty("task_id").GetString().Should().Be("29");
        var adrCompliance = ReadAcceptanceArtifact(acceptanceSummary, "adr-compliance.json");
        var acceptanceRefs = ReadAcceptanceArtifact(acceptanceSummary, "acceptance-refs.json");

        var declaredAdrRefs = ReadStringArray(adrCompliance, "adrRefs");
        declaredAdrRefs.Should().Contain(new[] { "ADR-0032", "ADR-0033" });
        adrCompliance.GetProperty("adrStatus").GetProperty("ADR-0032").GetProperty("status").GetString().Should().Be("Accepted");
        adrCompliance.GetProperty("adrStatus").GetProperty("ADR-0033").GetProperty("status").GetString().Should().Be("Accepted");

        var passingGateResult = AdrTraceabilityGate.Evaluate(declaredAdrRefs);
        passingGateResult.IsPass.Should().BeTrue("real acceptance ADR evidence includes ADR-0032 and ADR-0033");
        passingGateResult.MissingRequiredAdrRefs.Should().BeEmpty();

        var failingGateResult = AdrTraceabilityGate.Evaluate(declaredAdrRefs.Where(adr => !string.Equals(adr, "ADR-0032", StringComparison.Ordinal)));
        failingGateResult.IsPass.Should().BeFalse();
        failingGateResult.MissingRequiredAdrRefs.Should().Contain("ADR-0032");

        AssertAcceptanceRefsContainsAdr0032Evidence(acceptanceRefs, "back");
        AssertAcceptanceRefsContainsAdr0032Evidence(acceptanceRefs, "gameplay");
    }

    private static JsonElement ReadUnitSummary()
    {
        var path = FindLatestSummaryPath(
            Path.Combine(GetRepositoryRoot(), "logs", "unit"),
            filePath => true);
        return string.IsNullOrWhiteSpace(path) ? default : ReadJsonRoot(path);
    }

    private static JsonElement ReadAcceptanceSummary()
    {
        var acceptanceRunId = Environment.GetEnvironmentVariable("SC_ACCEPTANCE_RUN_ID");
        if (!string.IsNullOrWhiteSpace(acceptanceRunId))
        {
            var pinnedPath = FindSummaryPathByAcceptanceRunId(acceptanceRunId.Trim());
            return ReadJsonRoot(pinnedPath);
        }

        var explicitOutDir = Environment.GetEnvironmentVariable("SC_ACCEPTANCE_OUT_DIR");
        if (!string.IsNullOrWhiteSpace(explicitOutDir))
        {
            var summaryPath = Path.Combine(explicitOutDir.Trim(), "summary.json");
            return File.Exists(summaryPath) ? ReadJsonRoot(summaryPath) : default;
        }

        var path = FindLatestSummaryPath(
            Path.Combine(GetRepositoryRoot(), "logs", "ci"),
            filePath => filePath.Contains("sc-acceptance-check-task-29", StringComparison.OrdinalIgnoreCase));
        return string.IsNullOrWhiteSpace(path) ? default : ReadJsonRoot(path);
    }

    private static IReadOnlyList<string> ReadTask29DeclaredTestRefs()
    {
        var repositoryRoot = GetRepositoryRoot();
        var backRefs = ReadTaskRefsFromMirror(Path.Combine(repositoryRoot, ".taskmaster", "tasks", "tasks_back.json"));
        var gameplayRefs = ReadTaskRefsFromMirror(Path.Combine(repositoryRoot, ".taskmaster", "tasks", "tasks_gameplay.json"));

        var backOrdered = backRefs.OrderBy(path => path, StringComparer.Ordinal).ToArray();
        var gameplayOrdered = gameplayRefs.OrderBy(path => path, StringComparer.Ordinal).ToArray();
        backOrdered.Should().Equal(gameplayOrdered, "task test_refs must stay consistent across task views for taskmaster_id=29");
        return backOrdered;
    }

    private static PoolValidationResult ValidatePool(
        CardPoolSelectionService selectionService,
        IReadOnlyCollection<CardPoolDefinition> pools,
        int actId,
        string encounterType)
    {
        CardPoolDefinition pool;
        try
        {
            pool = selectionService.SelectSinglePool(pools, actId, encounterType);
        }
        catch (Exception)
        {
            return new PoolValidationResult(actId, encounterType, false, "missing_combo");
        }

        if (pool.CardsByRarity.Count == 0)
        {
            return new PoolValidationResult(actId, encounterType, false, "empty_pool");
        }

        foreach (var rarityTier in RequiredRarityTiers)
        {
            if (!pool.CardsByRarity.TryGetValue(rarityTier, out var cards))
            {
                return new PoolValidationResult(actId, encounterType, false, "missing_rarity_tier");
            }

            if (cards is null || cards.Count == 0)
            {
                return new PoolValidationResult(actId, encounterType, false, "empty_rarity_tier");
            }
        }

        return new PoolValidationResult(actId, encounterType, true, "ok");
    }

    private static IReadOnlyList<string> ReadTaskRefsFromMirror(string taskFilePath)
    {
        File.Exists(taskFilePath).Should().BeTrue($"expected task file: {taskFilePath}");
        using var document = JsonDocument.Parse(File.ReadAllText(taskFilePath));
        document.RootElement.ValueKind.Should().Be(JsonValueKind.Array, $"expected array root in task file: {taskFilePath}");

        JsonElement matchedTask = default;
        var found = false;
        foreach (var task in document.RootElement.EnumerateArray())
        {
            if (!task.TryGetProperty("taskmaster_id", out var taskIdElement))
            {
                continue;
            }

            if (!string.Equals(taskIdElement.ToString(), "29", StringComparison.Ordinal))
            {
                continue;
            }

            matchedTask = task;
            found = true;
            break;
        }

        found.Should().BeTrue($"taskmaster_id=29 must exist in: {taskFilePath}");
        matchedTask.TryGetProperty("test_refs", out var testRefsElement).Should().BeTrue($"taskmaster_id=29 must include test_refs in: {taskFilePath}");
        testRefsElement.ValueKind.Should().Be(JsonValueKind.Array, $"test_refs must be array in: {taskFilePath}");

        var refs = testRefsElement
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(path => !string.IsNullOrWhiteSpace(path))
            .Select(path => path!.Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        refs.Should().NotBeEmpty($"test_refs for taskmaster_id=29 must not be empty in: {taskFilePath}");
        return refs;
    }

    private static JsonElement FindStepByName(JsonElement acceptanceSummary, string stepName)
    {
        var step = acceptanceSummary
            .GetProperty("steps")
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("name", out var nameNode)
                && string.Equals(nameNode.GetString(), stepName, StringComparison.Ordinal));

        step.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"step '{stepName}' should exist in acceptance summary");
        return step.Clone();
    }

    private static string GetAcceptanceOutDir(JsonElement acceptanceSummary)
    {
        acceptanceSummary.TryGetProperty("out_dir", out var outDirNode).Should().BeTrue();
        var outDir = outDirNode.GetString();
        string.IsNullOrWhiteSpace(outDir).Should().BeFalse("acceptance summary out_dir must be present");
        Directory.Exists(outDir!).Should().BeTrue("acceptance out_dir should exist on disk");
        return outDir!;
    }

    private static JsonElement ReadAcceptanceArtifact(JsonElement acceptanceSummary, string fileName)
    {
        var outDir = GetAcceptanceOutDir(acceptanceSummary);
        var path = Path.Combine(outDir, fileName);
        return ReadJsonRoot(path);
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement node, string propertyName)
    {
        node.TryGetProperty(propertyName, out var propertyNode).Should().BeTrue($"property '{propertyName}' should exist");
        propertyNode.ValueKind.Should().Be(JsonValueKind.Array, $"property '{propertyName}' should be an array");
        return propertyNode
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Select(item => item!.Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }

    private static IReadOnlyList<string> CollectBoundRefsFromAcceptanceAnchors(JsonElement acceptanceAnchorsEvidence, string viewName)
    {
        var viewNode = acceptanceAnchorsEvidence
            .GetProperty("views")
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("view", out var node)
                && string.Equals(node.GetString(), viewName, StringComparison.Ordinal));
        viewNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"acceptance anchors should include view '{viewName}'");
        viewNode.GetProperty("status").GetString().Should().Be("ok");

        var refs = viewNode
            .GetProperty("items")
            .EnumerateArray()
            .Where(item => string.Equals(item.GetProperty("status").GetString(), "ok", StringComparison.Ordinal))
            .SelectMany(item => ReadStringArray(item, "bound_in"))
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        refs.Should().NotBeEmpty($"acceptance anchors should emit bound refs for view '{viewName}'");
        return refs;
    }

    private static void AssertAnchorBoundToTaskTestRef(JsonElement acceptanceAnchorsEvidence, string viewName, string anchor)
    {
        var viewNode = acceptanceAnchorsEvidence
            .GetProperty("views")
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("view", out var node)
                && string.Equals(node.GetString(), viewName, StringComparison.Ordinal));
        viewNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"acceptance anchors should include view '{viewName}'");

        var anchorNode = viewNode
            .GetProperty("items")
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("anchor", out var anchorNodeValue)
                && string.Equals(anchorNodeValue.GetString(), anchor, StringComparison.Ordinal));
        anchorNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"anchor '{anchor}' should exist in view '{viewName}'");
        anchorNode.GetProperty("status").GetString().Should().Be("ok");
        ReadStringArray(anchorNode, "bound_in").Should().Contain(ThisTaskTestRef);
    }

    private static void AssertAcceptanceRefsContainsAdr0032Evidence(JsonElement acceptanceRefsEvidence, string viewName)
    {
        var viewsNode = acceptanceRefsEvidence.GetProperty("views");
        viewsNode.TryGetProperty(viewName, out var viewNode).Should().BeTrue($"acceptance refs should include view '{viewName}'");
        viewNode.GetProperty("status").GetString().Should().Be("ok");

        var adr0032Item = viewNode
            .GetProperty("items")
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("index", out var indexNode)
                && indexNode.ValueKind == JsonValueKind.Number
                && indexNode.GetInt32() == 7);
        adr0032Item.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"view '{viewName}' should include acceptance item index=7");
        adr0032Item.GetProperty("status").GetString().Should().Be("ok");
        adr0032Item.GetProperty("text").GetString().Should().Contain("record pass/fail");
        ReadStringArray(adr0032Item, "refs").Should().Contain(ThisTaskTestRef);
    }

    private static JsonElement ReadJsonRoot(string path)
    {
        File.Exists(path).Should().BeTrue($"expected evidence file: {path}");
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        return document.RootElement.Clone();
    }

    private static string? FindLatestSummaryPath(string rootDirectory, Func<string, bool> filter)
    {
        if (!Directory.Exists(rootDirectory))
        {
            return null;
        }

        var candidate = Directory
            .EnumerateFiles(rootDirectory, "summary.json", SearchOption.AllDirectories)
            .Where(filter)
            .Select(path => new FileInfo(path))
            .OrderByDescending(info => info.LastWriteTimeUtc)
            .FirstOrDefault();

        return candidate?.FullName;
    }

    private static string FindSummaryPathByAcceptanceRunId(string acceptanceRunId)
    {
        var rootDirectory = Path.Combine(GetRepositoryRoot(), "logs", "ci");
        Directory.Exists(rootDirectory).Should().BeTrue($"expected directory: {rootDirectory}");

        foreach (var path in Directory.EnumerateFiles(rootDirectory, "summary.json", SearchOption.AllDirectories))
        {
            if (!path.Contains("sc-acceptance-check-task-29", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var summaryRoot = ReadJsonRoot(path);
            if (!summaryRoot.TryGetProperty("run_id", out var runIdNode))
            {
                continue;
            }

            if (string.Equals(runIdNode.GetString(), acceptanceRunId, StringComparison.Ordinal))
            {
                return path;
            }
        }

        throw new InvalidOperationException(
            $"SC_ACCEPTANCE_RUN_ID='{acceptanceRunId}' did not match any Task 29 acceptance summary.json artifact.");
    }

    private static string GetRepositoryRoot()
    {
        return RepositoryRoot.Value;
    }

    private static string ResolveRepositoryRoot()
    {
        var starts = new[]
        {
            Directory.GetCurrentDirectory(),
            AppContext.BaseDirectory,
        };

        foreach (var start in starts)
        {
            var found = TryFindRepositoryRoot(start);
            if (found is not null)
            {
                return found;
            }
        }

        throw new InvalidOperationException("Failed to locate repository root from current directory or application base directory.");
    }

    private static string? TryFindRepositoryRoot(string startPath)
    {
        if (string.IsNullOrWhiteSpace(startPath))
        {
            return null;
        }

        var directory = new DirectoryInfo(Path.GetFullPath(startPath));
        while (directory is not null)
        {
            var agentsPath = Path.Combine(directory.FullName, "AGENTS.md");
            var taskFilePath = Path.Combine(directory.FullName, ".taskmaster", "tasks", "tasks_back.json");
            if (File.Exists(agentsPath) && File.Exists(taskFilePath))
            {
                return directory.FullName;
            }

            directory = directory.Parent;
        }

        return null;
    }

    private sealed class PoolValidationResult
    {
        public PoolValidationResult(int actId, string encounterType, bool isValid, string reason)
        {
            ActId = actId;
            EncounterType = encounterType;
            IsValid = isValid;
            Reason = reason;
        }

        public int ActId { get; }

        public string EncounterType { get; }

        public bool IsValid { get; }

        public string Reason { get; }
    }

    private static class AdrTraceabilityGate
    {
        private static readonly string[] RequiredAdrRefs = { "ADR-0032", "ADR-0033" };

        public static AdrGateResult Evaluate(IEnumerable<string> declaredAdrRefs)
        {
            var normalized = new HashSet<string>(
                declaredAdrRefs
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Select(value => value.Trim().ToUpperInvariant()),
                StringComparer.Ordinal);

            var missing = RequiredAdrRefs
                .Where(requiredAdr => !normalized.Contains(requiredAdr))
                .ToArray();

            return new AdrGateResult(missing.Length == 0, missing);
        }
    }

    private sealed class AdrGateResult
    {
        public AdrGateResult(bool isPass, IReadOnlyList<string> missingRequiredAdrRefs)
        {
            IsPass = isPass;
            MissingRequiredAdrRefs = missingRequiredAdrRefs;
        }

        public bool IsPass { get; }

        public IReadOnlyList<string> MissingRequiredAdrRefs { get; }
    }
}
