using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using Xunit.Sdk;

namespace Game.Core.Tests.Tasks;

internal static class Task1PreflightEvidenceGuard
{
    private const string StrictEnvName = "TASK1_PREFLIGHT_REQUIRED";
    private const string SolutionFileName = "NewRouge.sln";

    internal static bool TryGetTodayArtifact(out Task1PreflightArtifact artifact, out string reason)
    {
        var repoRoot = FindRepoRoot();
        var dateSegment = DateTime.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        var taskJsonPath = Path.Combine(repoRoot, "logs", "ci", dateSegment, "task-0001.json");
        var evidenceDirectory = Path.Combine(repoRoot, "logs", "ci", dateSegment, "env-evidence");

        var missing = new List<string>();
        if (!File.Exists(taskJsonPath))
        {
            missing.Add(taskJsonPath);
        }

        if (!Directory.Exists(evidenceDirectory))
        {
            missing.Add(evidenceDirectory);
        }

        if (missing.Count > 0)
        {
            artifact = default;
            reason = "missing preflight evidence: " + string.Join(", ", missing);
            return false;
        }

        artifact = new Task1PreflightArtifact(repoRoot, dateSegment, taskJsonPath, evidenceDirectory);
        reason = string.Empty;
        return true;
    }

    internal static void EnsureOrSkip(string reason)
    {
        if (!ShouldEnforcePreflight())
        {
            return;
        }

        throw new XunitException(
            "Task1 preflight evidence is required but missing. " +
            reason +
            " Set TASK1_PREFLIGHT_REQUIRED=0 (or unset) to suppress in non-Task1 runs.");
    }

    private static bool ShouldEnforcePreflight()
    {
        var raw = Environment.GetEnvironmentVariable(StrictEnvName);
        if (string.IsNullOrWhiteSpace(raw))
        {
            return false;
        }

        return raw.Equals("1", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("true", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("yes", StringComparison.OrdinalIgnoreCase)
               || raw.Equals("on", StringComparison.OrdinalIgnoreCase);
    }

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, SolutionFileName)))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new InvalidOperationException(
            "Unable to locate repository root containing " + SolutionFileName + ".");
    }
}

internal readonly record struct Task1PreflightArtifact(
    string RepoRoot,
    string DateSegment,
    string TaskJsonPath,
    string EvidenceDirectory);
