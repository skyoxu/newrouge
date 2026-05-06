using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0103WorkflowSelectionEvidenceTests
{
    private const int TaskmasterId = 103;
    private const string TasksBackPath = ".taskmaster/tasks/tasks_back.json";
    private const string ThisTaskTestRef = "Game.Core.Tests/Tasks/Task0103WorkflowSelectionEvidenceTests.cs";
    private const string AuditDocRef = "docs/gdd/t1-t69-m1-wiring-audit.md";

    // ACC:T103.1
    // ACC:T103.2
    // ACC:T103.3
    // ACC:T103.4
    // ACC:T103.5
    [Fact]
    public void ShouldKeepTask103AsGovernanceOnlySplitEvidence_WhenReadingTask103Metadata()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var acceptance = ReadStringArray(task, "acceptance");
        var testRefs = ReadStringArray(task, "test_refs");
        var evidenceRefs = ReadStringArray(task, "evidence_refs");
        var labels = ReadStringArray(task, "labels");

        acceptance.Length.Should().BeGreaterThanOrEqualTo(5);
        acceptance.Should().OnlyContain(line => line.Contains("Refs: " + ThisTaskTestRef, StringComparison.Ordinal));
        acceptance.Should().Contain(line =>
            line.Contains("two distinct lanes", StringComparison.OrdinalIgnoreCase)
            && line.Contains("primary boundaries", StringComparison.OrdinalIgnoreCase)
            && line.Contains("locked surfaces", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("T87", StringComparison.Ordinal)
            && line.Contains("T98", StringComparison.Ordinal)
            && line.Contains("independently", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("must not add gameplay feature implementation", StringComparison.OrdinalIgnoreCase));
        acceptance.Should().Contain(line =>
            line.Contains("workflow has not selected T103", StringComparison.OrdinalIgnoreCase)
            && line.Contains("no implementation work may advance", StringComparison.OrdinalIgnoreCase));

        testRefs.Should().ContainSingle().Which.Should().Be(ThisTaskTestRef);
        evidenceRefs.Should().Contain(AuditDocRef);
        labels.Should().Contain("workflow");
        labels.Should().Contain("resume");
        labels.Should().Contain("review");

        var layer = task.TryGetProperty("layer", out var layerNode) ? layerNode.GetString() ?? string.Empty : string.Empty;
        layer.Should().Be("docs");
    }

    // ACC:T103.1
    // ACC:T103.2
    [Fact]
    public void ShouldRequireAuditDocumentToMentionContinueSplitGovernanceScope_WhenValidatingEvidenceCarrier()
    {
        var content = ReadRepoText(AuditDocRef);

        content.Should().Contain("T102-T104");
        content.Should().Contain("T103");
        content.Should().Contain("Continue");
        content.Should().Contain("review / recovery");
    }

    // ACC:T103.3
    [Fact]
    public void ShouldExposeTask87AndTask98AsDependencies_WhenReadingTask103DependencyBoundary()
    {
        var task = ReadTaskNode(TasksBackPath, TaskmasterId);
        var dependsOn = ReadStringArray(task, "depends_on");

        dependsOn.Should().Contain("NG-0062");
        dependsOn.Should().Contain("NG-0070");
        dependsOn.Should().Contain("NG-0074");
    }

    private static JsonElement ReadTaskNode(string taskFilePath, int taskmasterId)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), taskFilePath.Replace('/', Path.DirectorySeparatorChar));
        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        var task = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(node =>
                node.TryGetProperty("taskmaster_id", out var idNode)
                && idNode.ValueKind == JsonValueKind.Number
                && idNode.GetInt32() == taskmasterId);

        task.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"taskmaster_id={taskmasterId} must exist in {taskFilePath}");
        return JsonDocument.Parse(task.GetRawText()).RootElement.Clone();
    }

    private static string[] ReadStringArray(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return property.EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string ReadRepoText(string repoRelativePath)
    {
        var root = FindRepositoryRoot();
        var absolutePath = Path.Combine(root, repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"required evidence file missing: {repoRelativePath}");
        return File.ReadAllText(absolutePath);
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

        throw new DirectoryNotFoundException("Unable to locate repository root containing NewRouge.sln.");
    }
}
