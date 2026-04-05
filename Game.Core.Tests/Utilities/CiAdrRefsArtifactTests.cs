using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Utilities;

public sealed class CiAdrRefsArtifactTests
{
    private const int TaskId = 11;
    private static readonly string[] RequiredAdrRefs = { "ADR-0021", "ADR-0032" };

    // ACC:T11.29
    [Fact]
    public void ShouldContainMachineReadableAdrRefs_WhenTask11CiArtifactsAreCollected()
    {
        var artifactPaths = FindTaskCiArtifacts(TaskId).ToArray();

        artifactPaths.Should().NotBeEmpty(
            "RED-FIRST: CI must emit task-0011 artifact files before this acceptance can pass.");

        foreach (var artifactPath in artifactPaths)
        {
            using var document = JsonDocument.Parse(File.ReadAllText(artifactPath));
            var validationPassed = TryValidateAdrRefs(document.RootElement, out var validationError);

            validationPassed.Should().BeTrue($"{artifactPath} must include machine-readable adr_refs. {validationError}");
        }
    }

    [Fact]
    public void ShouldRejectArtifact_WhenAdrRefsFieldIsMissing()
    {
        const string artifactJson = "{\"task_id\":11,\"result\":\"pass\"}";
        using var document = JsonDocument.Parse(artifactJson);

        var validationPassed = TryValidateAdrRefs(document.RootElement, out var validationError);

        validationPassed.Should().BeFalse();
        validationError.Should().Contain("adr_refs");
    }

    [Fact]
    public void ShouldRejectArtifact_WhenAdrRefsContainsNonStringValue()
    {
        const string artifactJson = "{\"task_id\":11,\"adr_refs\":[\"ADR-0021\",123]}";
        using var document = JsonDocument.Parse(artifactJson);

        var validationPassed = TryValidateAdrRefs(document.RootElement, out var validationError);

        validationPassed.Should().BeFalse();
        validationError.Should().Contain("string");
    }

    [Fact]
    public void ShouldAcceptArtifact_WhenAdrRefsContainsRequiredBacklinks()
    {
        const string artifactJson = "{\"task_id\":11,\"adr_refs\":[\"ADR-0021\",\"ADR-0032\"]}";
        using var document = JsonDocument.Parse(artifactJson);

        var validationPassed = TryValidateAdrRefs(document.RootElement, out var validationError);

        validationPassed.Should().BeTrue(validationError);
    }

    private static IEnumerable<string> FindTaskCiArtifacts(int taskId)
    {
        var repoRoot = FindRepoRoot();
        var ciRoot = Path.Combine(repoRoot, "logs", "ci");
        if (!Directory.Exists(ciRoot))
        {
            return Array.Empty<string>();
        }

        var expectedFileName = $"task-{taskId:D4}.json";
        return Directory
            .EnumerateFiles(ciRoot, expectedFileName, SearchOption.AllDirectories)
            .OrderBy(path => path, StringComparer.Ordinal)
            .ToArray();
    }

    private static bool TryValidateAdrRefs(JsonElement artifact, out string validationError)
    {
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

        var adrRefs = new List<string>();
        foreach (var adrRefElement in adrRefsProperty.EnumerateArray())
        {
            if (adrRefElement.ValueKind != JsonValueKind.String)
            {
                validationError = "adr_refs entries must be string values.";
                return false;
            }

            var adrRef = adrRefElement.GetString();
            if (string.IsNullOrWhiteSpace(adrRef))
            {
                validationError = "adr_refs entries must not be empty.";
                return false;
            }

            adrRefs.Add(adrRef);
        }

        if (!RequiredAdrRefs.All(requiredAdr => adrRefs.Contains(requiredAdr, StringComparer.Ordinal)))
        {
            validationError = $"adr_refs must contain required backlinks: {string.Join(", ", RequiredAdrRefs)}.";
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
