using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Utilities;

public sealed class AdrTraceabilityTests
{
    private const int TaskId = 11;
    private const string StrictEvidenceEnvName = "TASK0011_CI_ADR_ARTIFACTS_REQUIRED";
    private const string TaskViewPath = ".taskmaster/tasks/tasks_gameplay.json";
    private const string ThisTestRef = "Game.Core.Tests/Utilities/AdrTraceabilityTests.cs";
    private static readonly string[] RequiredAdrRefs = { "ADR-0021", "ADR-0032" };

    // ACC:T11.28
    [Fact]
    public void ShouldRequireAdr0021AndAdr0032_WhenTask11AcceptanceBacklinksReferenceThisTest()
    {
        var task11 = LoadTaskById(TaskViewPath, TaskId);
        var acceptanceItems = EnumerateStringArray(task11, "acceptance").ToArray();

        var acceptanceItemsBoundToThisFile = acceptanceItems
            .Where(item => ParseRefs(item).Contains(ThisTestRef, StringComparer.Ordinal))
            .ToArray();

        acceptanceItemsBoundToThisFile.Should().NotBeEmpty(
            "Task 11 acceptance must explicitly bind this evidence test via Refs.");

        acceptanceItemsBoundToThisFile.Should().Contain(
            item => RequiredAdrRefs.All(adr => item.Contains(adr, StringComparison.Ordinal)),
            "Task 11 acceptance must explicitly require backlinks to ADR-0021 and ADR-0032.");

        var taskAdrRefs = EnumerateStringArray(task11, "adr_refs").ToArray();
        taskAdrRefs.Should().Contain(RequiredAdrRefs);
    }

    // ACC:T11.29
    [Fact]
    public void ShouldContainMachineReadableAdrRefs_WhenTask11CiArtifactsAreCollected()
    {
        var ciArtifacts = FindTaskCiArtifacts(TaskId).ToArray();
        if (ciArtifacts.Length == 0 && !ShouldRequireCiArtifacts())
        {
            return;
        }

        ciArtifacts.Should().NotBeEmpty(
            "RED-FIRST: CI must emit task-0011 artifacts before this acceptance can turn green.");

        foreach (var artifactPath in ciArtifacts)
        {
            using var document = JsonDocument.Parse(File.ReadAllText(artifactPath));
            var validationPassed = TryReadRequiredAdrRefs(document.RootElement, out _, out var validationError);

            validationPassed.Should().BeTrue($"{artifactPath} must expose machine-readable adr_refs. {validationError}");
        }
    }

    private static bool ShouldRequireCiArtifacts()
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

    [Fact]
    public void ShouldRejectArtifact_WhenAdrRefsFieldIsMissing()
    {
        const string artifactJson = "{\"task_id\":11,\"result\":\"pass\"}";
        using var document = JsonDocument.Parse(artifactJson);

        var validationPassed = TryReadRequiredAdrRefs(document.RootElement, out _, out var validationError);

        validationPassed.Should().BeFalse();
        validationError.Should().Contain("adr_refs");
    }

    private static JsonElement LoadTaskById(string repoRelativePath, int taskId)
    {
        var absolutePath = Path.Combine(FindRepoRoot(), repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"expected repository file at {repoRelativePath}");

        using var document = JsonDocument.Parse(File.ReadAllText(absolutePath));
        document.RootElement.ValueKind.Should().Be(JsonValueKind.Array, $"{repoRelativePath} must be an array view file");

        foreach (var task in document.RootElement.EnumerateArray())
        {
            if (!task.TryGetProperty("taskmaster_id", out var idProperty))
            {
                continue;
            }

            if (TryReadTaskId(idProperty, out var currentId) && currentId == taskId)
            {
                return task.Clone();
            }
        }

        throw new InvalidOperationException($"Task {taskId} was not found in {repoRelativePath}.");
    }

    private static bool TryReadTaskId(JsonElement idProperty, out int id)
    {
        id = default;
        return idProperty.ValueKind switch
        {
            JsonValueKind.Number => idProperty.TryGetInt32(out id),
            JsonValueKind.String => int.TryParse(idProperty.GetString(), out id),
            _ => false,
        };
    }

    private static IEnumerable<string> EnumerateStringArray(JsonElement item, string propertyName)
    {
        if (!item.TryGetProperty(propertyName, out var property) || property.ValueKind != JsonValueKind.Array)
        {
            yield break;
        }

        foreach (var element in property.EnumerateArray())
        {
            var value = element.GetString();
            if (!string.IsNullOrWhiteSpace(value))
            {
                yield return value!;
            }
        }
    }

    private static IEnumerable<string> ParseRefs(string acceptanceItem)
    {
        var refsIndex = acceptanceItem.IndexOf("Refs:", StringComparison.OrdinalIgnoreCase);
        if (refsIndex < 0)
        {
            yield break;
        }

        var refsText = acceptanceItem[(refsIndex + "Refs:".Length)..];
        var tokens = refsText
            .Replace(',', ' ')
            .Split(' ', StringSplitOptions.RemoveEmptyEntries);

        foreach (var token in tokens)
        {
            var normalized = token.Trim();
            if (!string.IsNullOrWhiteSpace(normalized))
            {
                yield return normalized;
            }
        }
    }

    private static IEnumerable<string> FindTaskCiArtifacts(int taskId)
    {
        var repoRoot = FindRepoRoot();
        var ciRoot = Path.Combine(repoRoot, "logs", "ci");
        if (!Directory.Exists(ciRoot))
        {
            return Array.Empty<string>();
        }

        var fileName = $"task-{taskId:D4}.json";
        return Directory
            .EnumerateFiles(ciRoot, fileName, SearchOption.AllDirectories)
            .OrderBy(path => path, StringComparer.Ordinal)
            .ToArray();
    }

    private static bool TryReadRequiredAdrRefs(JsonElement artifact, out IReadOnlyCollection<string> adrRefs, out string validationError)
    {
        adrRefs = Array.Empty<string>();
        validationError = string.Empty;

        if (!artifact.TryGetProperty("adr_refs", out var adrRefsProperty))
        {
            validationError = "Missing machine-readable adr_refs field.";
            return false;
        }

        if (adrRefsProperty.ValueKind != JsonValueKind.Array)
        {
            validationError = "adr_refs must be a JSON array.";
            return false;
        }

        var parsedAdrRefs = adrRefsProperty
            .EnumerateArray()
            .Where(element => element.ValueKind == JsonValueKind.String)
            .Select(element => element.GetString())
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value!)
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        adrRefs = parsedAdrRefs;

        if (!RequiredAdrRefs.All(requiredAdr => parsedAdrRefs.Contains(requiredAdr, StringComparer.Ordinal)))
        {
            validationError = "adr_refs must contain ADR-0021 and ADR-0032.";
            return false;
        }

        return true;
    }

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new InvalidOperationException("Unable to locate repository root.");
    }
}
