using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task1EnvironmentEvidencePersistenceTests
{
    private static readonly TimeSpan CommandTimeout = TimeSpan.FromSeconds(20);
    private static readonly string[] RequiredEvidenceFiles =
    {
        "godot-bin-env.txt",
        "godot-version.txt",
        "godot-bin-version.txt",
        "dotnet-version.txt",
        "dotnet-sdks.txt",
        "dotnet-restore.txt",
        "packages-lock-exists.txt",
        "windows-only-check.txt",
        "utf8-check.txt",
    };

    private static readonly string[] RequiredAdrs = { "ADR-0031", "ADR-0011" };
    private static readonly Regex ChecklistPathRegex = new("(?<=`)(logs/[^\r\n`]+)(?=`)", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex AdrRegex = new(@"\bADR-\d{4}\b", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private const string ChecklistRelativePath = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md";
    private const string Task1ChecklistSectionToken = "ACC:T1.3";
    private const string DateToken = "<YYYY-MM-DD>";
    private static readonly string[] ChecklistSemanticAnchors =
    {
        "PRD-ID: PRD-NEWROUGE-GAME-0001",
        "ACC:T1.3",
        "Task1 Evidence Path Template",
    };
    private static readonly string[] ChecklistMojibakeMarkers =
    {
        "锛",
        "銆",
        "鈥",
        "锟",
        "�",
    };

    // ACC:T1.1
    // ACC:T1.2
    // ACC:T1.6
    // ACC:T1.10
    // ACC:T1.13
    [Fact]
    public async Task ShouldValidateMachineReadableArtifactAgainstRealEvidenceFiles_WhenTask1PreflightHasRun()
    {
        if (!TryLoadTodayTask0001Artifact(out var artifact))
        {
            return;
        }

        using var document = JsonDocument.Parse(artifact.TaskJsonText);
        var root = document.RootElement;

        var validation = ValidateTask0001MachineReadableFields(root, artifact.RepoRoot, artifact.DateSegment);
        validation.IsValid.Should().BeTrue(string.Join(Environment.NewLine, validation.Errors));

        var godotEvidence = Path.Combine(artifact.EvidenceDirectory, "godot-version.txt");
        var godotBinEvidence = Path.Combine(artifact.EvidenceDirectory, "godot-bin-version.txt");

        root.TryGetProperty("godot_bin", out var godotBinElement).Should().BeTrue("task-0001.json must include godot_bin");
        var godotBinPath = godotBinElement.GetString();
        godotBinPath.Should().NotBeNullOrWhiteSpace("task-0001.json godot_bin must be available for evidence verification");
        File.Exists(godotBinPath!).Should().BeTrue("task-0001.json godot_bin should point to an existing executable");

        var godotDirectory = Path.GetDirectoryName(godotBinPath!);
        godotDirectory.Should().NotBeNullOrWhiteSpace("GODOT_BIN directory is required for PATH-prefixed command execution");

        var godotFromPath = await RunProcessAsync(
            "powershell",
            "-NoProfile -ExecutionPolicy Bypass -Command \"godot --version\"",
            prependPath: godotDirectory);
        var godotFromEnvBin = await RunProcessAsync(godotBinPath!, "--version");

        NormalizeLineEndings(BuildCombinedOutput(godotFromEnvBin))
            .Should()
            .Be(
                NormalizeLineEndings(File.ReadAllText(godotBinEvidence)),
                "& $env:GODOT_BIN --version evidence file must persist full stdout/stderr stream");

        if (godotFromPath.ExitCode == 0)
        {
            NormalizeLineEndings(BuildCombinedOutput(godotFromPath))
                .Should()
                .Be(
                    NormalizeLineEndings(File.ReadAllText(godotEvidence)),
                    "when godot --version is available, evidence file must persist full stdout/stderr stream");
        }
    }

    // ACC:T1.3
    [Fact]
    public void ShouldResolveChecklistEvidencePathsAgainstRepository_WhenChecklistContainsConcreteFiles()
    {
        if (!TryLoadTodayTask0001Artifact(out var artifact))
        {
            return;
        }

        var checklistPath = Path.Combine(artifact.RepoRoot, ChecklistRelativePath.Replace("/", Path.DirectorySeparatorChar.ToString()));

        File.Exists(checklistPath).Should().BeTrue("ACCEPTANCE_CHECKLIST.md must exist");
        var checklistContent = ReadUtf8Strict(checklistPath);
        using var document = JsonDocument.Parse(artifact.TaskJsonText);
        var expectedEvidencePaths = document.RootElement
            .GetProperty("evidence_paths")
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(path => !string.IsNullOrWhiteSpace(path))
            .Cast<string>()
            .ToArray();

        var validation = ValidateChecklistEvidencePaths(checklistContent, artifact.RepoRoot, artifact.DateSegment, expectedEvidencePaths);
        validation.IsValid.Should().BeTrue(string.Join(Environment.NewLine, validation.Errors));
    }

    // ACC:T1.3
    [Fact]
    public void ShouldFailChecklistValidation_WhenChecklistContainsBrokenEvidencePath()
    {
        var repoRoot = FindRepoRoot();
        var dateSegment = DateTime.UtcNow.ToString("yyyy-MM-dd");
        var brokenChecklist = "## Task1 Evidence (" + Task1ChecklistSectionToken + ")" + Environment.NewLine
            + "- `logs/ci/2099-01-01/env-evidence/does-not-exist.txt`";
        var expectedEvidencePaths = RequiredEvidenceFiles
            .Select(file => $"logs/ci/{dateSegment}/env-evidence/{file}")
            .ToArray();

        var validation = ValidateChecklistEvidencePaths(brokenChecklist, repoRoot, dateSegment, expectedEvidencePaths);

        validation.IsValid.Should().BeFalse();
        validation.Errors.Should().ContainSingle(error => error.Contains("does-not-exist.txt", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T1.3
    [Fact]
    public void ShouldFailChecklistValidation_WhenTask1SectionContainsNonEnvEvidencePath()
    {
        var repoRoot = FindRepoRoot();
        var dateSegment = DateTime.UtcNow.ToString("yyyy-MM-dd");
        var expectedEvidencePaths = RequiredEvidenceFiles
            .Select(file => $"logs/ci/{dateSegment}/env-evidence/{file}")
            .ToArray();
        var checklist = "## Task1 Evidence (" + Task1ChecklistSectionToken + ")" + Environment.NewLine
            + "- `logs/ci/<YYYY-MM-DD>/other/foo.txt`" + Environment.NewLine;

        var validation = ValidateChecklistEvidencePaths(checklist, repoRoot, dateSegment, expectedEvidencePaths);

        validation.IsValid.Should().BeFalse();
        validation.Errors.Should().Contain(error => error.Contains("env-evidence path must use current date prefix", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T1.11
    // ACC:T1.12
    [Fact]
    public void ShouldRequireAdrBacklinksAndUtf8Pass_WhenReadingRealTaskArtifact()
    {
        if (!TryLoadTodayTask0001Artifact(out var artifact))
        {
            return;
        }

        var checklistPath = Path.Combine(artifact.RepoRoot, ChecklistRelativePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
        var checklistContent = ReadUtf8Strict(checklistPath);

        using var document = JsonDocument.Parse(artifact.TaskJsonText);
        var root = document.RootElement;

        var adrValidation = ValidateAdrBacklinks(root, checklistContent);
        adrValidation.IsValid.Should().BeTrue(string.Join(Environment.NewLine, adrValidation.Errors));

        var utf8Validation = ValidateUtf8Check(root, artifact.RepoRoot);
        utf8Validation.IsValid.Should().BeTrue(string.Join(Environment.NewLine, utf8Validation.Errors));
    }

    // ACC:T1.11
    [Fact]
    public void ShouldFailAdrValidation_WhenTaskArtifactMissesRequiredBacklinks()
    {
        var payload = JsonSerializer.Serialize(new
        {
            adr_refs = new[] { "ADR-0031" },
        });

        using var document = JsonDocument.Parse(payload);
        var validation = ValidateAdrBacklinks(document.RootElement, string.Empty);

        validation.IsValid.Should().BeFalse();
        validation.Errors.Should().Contain(error => error.Contains("ADR-0011", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T1.12
    [Fact]
    public void ShouldFailUtf8Validation_WhenUtf8ResultIsNotPassOrEvidencePathMissing()
    {
        var repoRoot = FindRepoRoot();
        var payload = JsonSerializer.Serialize(new
        {
            utf8_check = new
            {
                result = "fail",
                evidence_file = "logs/ci/2099-01-01/env-evidence/missing.txt",
            },
        });

        using var document = JsonDocument.Parse(payload);
        var validation = ValidateUtf8Check(document.RootElement, repoRoot);

        validation.IsValid.Should().BeFalse();
        validation.Errors.Should().Contain(error => error.Contains("utf8_check.result", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T1.12
    [Fact]
    public void ShouldFailUtf8Validation_WhenCheckedFilesDoNotCoverAllEnvEvidenceArtifacts()
    {
        if (!TryLoadTodayTask0001Artifact(out var artifact))
        {
            return;
        }

        var node = JsonNode.Parse(artifact.TaskJsonText)!.AsObject();

        var checkedFiles = node["utf8_check"]?["checked_files"]?.AsArray();
        checkedFiles.Should().NotBeNull("utf8_check.checked_files must exist in Task1 artifact");
        ArgumentNullException.ThrowIfNull(checkedFiles);

        var missingPath = $"logs/ci/{artifact.DateSegment}/env-evidence/dotnet-restore.txt";
        var targetNode = checkedFiles.FirstOrDefault(item =>
            string.Equals(item?.GetValue<string>(), missingPath, StringComparison.OrdinalIgnoreCase));
        targetNode.Should().NotBeNull("test precondition requires dotnet-restore evidence to exist in checked_files");
        checkedFiles.Remove(targetNode!);

        using var document = JsonDocument.Parse(node.ToJsonString());
        var validation = ValidateUtf8Check(document.RootElement, artifact.RepoRoot);

        validation.IsValid.Should().BeFalse();
        validation.Errors.Should().Contain(error => error.Contains("dotnet-restore.txt", StringComparison.OrdinalIgnoreCase));
    }

    // ACC:T1.12
    [Fact]
    public void ShouldFailUtf8Validation_WhenChecklistIsUtf8ButSemanticAnchorsAreCorrupted()
    {
        var tempRoot = Path.Combine(Path.GetTempPath(), "newrouge-task1-utf8-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            var date = "2099-01-01";
            var envDir = Path.Combine(tempRoot, "logs", "ci", date, "env-evidence");
            Directory.CreateDirectory(envDir);

            var taskJsonRel = $"logs/ci/{date}/task-0001.json";
            var checklistRel = ChecklistRelativePath;
            var checkedFiles = new List<string> { taskJsonRel, checklistRel };
            var evidencePaths = new List<string>();

            foreach (var fileName in RequiredEvidenceFiles)
            {
                var rel = $"logs/ci/{date}/env-evidence/{fileName}";
                var abs = Path.Combine(tempRoot, rel.Replace("/", Path.DirectorySeparatorChar.ToString()));
                Directory.CreateDirectory(Path.GetDirectoryName(abs)!);
                File.WriteAllText(abs, "ok", Encoding.UTF8);
                checkedFiles.Add(rel);
                evidencePaths.Add(rel);
            }

            var taskJsonAbs = Path.Combine(tempRoot, taskJsonRel.Replace("/", Path.DirectorySeparatorChar.ToString()));
            Directory.CreateDirectory(Path.GetDirectoryName(taskJsonAbs)!);
            File.WriteAllText(taskJsonAbs, "{\"task_id\":\"1\"}", Encoding.UTF8);

            var checklistAbs = Path.Combine(tempRoot, checklistRel.Replace("/", Path.DirectorySeparatorChar.ToString()));
            Directory.CreateDirectory(Path.GetDirectoryName(checklistAbs)!);
            File.WriteAllText(
                checklistAbs,
                "# 08莽芦聽验收清单\n## 七、Task1 鐜璇佹嵁璺緞妯℃澘\n",
                Encoding.UTF8);

            var payload = JsonSerializer.Serialize(new
            {
                evidence_paths = evidencePaths,
                utf8_check = new
                {
                    result = "pass",
                    evidence_file = $"logs/ci/{date}/env-evidence/utf8-check.txt",
                    checked_files = checkedFiles,
                },
            });

            using var document = JsonDocument.Parse(payload);
            var validation = ValidateUtf8Check(document.RootElement, tempRoot);
            validation.IsValid.Should().BeFalse();
            validation.Errors.Should().Contain(error => error.Contains("semantic anchor", StringComparison.OrdinalIgnoreCase));
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    [Theory]
    [InlineData("godot_bin_env.env_var_name", "godot_bin_env.env_var_name")]
    [InlineData("godot_bin_env.env_var_value", "godot_bin_env.env_var_value")]
    [InlineData("godot_bin_env.env_var_scope", "godot_bin_env.env_var_scope")]
    [InlineData("godot_bin_check.installation_verification_result", "installation_verification_result")]
    public void ShouldFailValidation_WhenRequiredGodotBinFieldsAreMissing(string pathToRemove, string expectedErrorFragment)
    {
        if (!TryLoadTodayTask0001Artifact(out var artifact))
        {
            return;
        }

        var node = JsonNode.Parse(artifact.TaskJsonText)!.AsObject();
        RemoveJsonPath(node, pathToRemove);

        using var document = JsonDocument.Parse(node.ToJsonString());
        var validation = ValidateTask0001MachineReadableFields(document.RootElement, artifact.RepoRoot, artifact.DateSegment);

        validation.IsValid.Should().BeFalse();
        validation.Errors.Should().Contain(error => error.Contains(expectedErrorFragment, StringComparison.OrdinalIgnoreCase));
    }

    private static bool TryLoadTodayTask0001Artifact(out Task0001Artifact artifact)
    {
        if (!Task1PreflightEvidenceGuard.TryGetTodayArtifact(out var preflight, out var missingReason))
        {
            Task1PreflightEvidenceGuard.EnsureOrSkip(missingReason);
            artifact = new Task0001Artifact(
                string.Empty,
                string.Empty,
                string.Empty,
                string.Empty,
                "{}");
            return false;
        }

        var taskJsonText = ReadUtf8Strict(preflight.TaskJsonPath);
        artifact = new Task0001Artifact(
            preflight.RepoRoot,
            preflight.DateSegment,
            preflight.TaskJsonPath,
            preflight.EvidenceDirectory,
            taskJsonText);
        return true;
    }

    private static ValidationResult ValidateTask0001MachineReadableFields(JsonElement root, string repoRoot, string dateSegment)
    {
        var errors = new List<string>();

        if (!root.TryGetProperty("godot_version", out _)) errors.Add("missing godot_version");
        if (!root.TryGetProperty("dotnet_version", out _)) errors.Add("missing dotnet_version");
        if (!root.TryGetProperty("dotnet_sdk_versions", out _)) errors.Add("missing dotnet_sdk_versions");
        if (!root.TryGetProperty("packages_lock_exists", out _)) errors.Add("missing packages_lock_exists");
        if (!root.TryGetProperty("godot_bin_env", out var godotBinEnv) || godotBinEnv.ValueKind != JsonValueKind.Object)
        {
            errors.Add("missing godot_bin_env object");
        }
        else
        {
            var envVarName = godotBinEnv.TryGetProperty("env_var_name", out var envVarNameElement)
                ? envVarNameElement.GetString()
                : null;
            if (!string.Equals(envVarName, "GODOT_BIN", StringComparison.Ordinal))
            {
                errors.Add("godot_bin_env.env_var_name must be GODOT_BIN");
            }

            var envVarValue = godotBinEnv.TryGetProperty("env_var_value", out var envVarValueElement)
                ? envVarValueElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(envVarValue) || !Path.IsPathRooted(envVarValue))
            {
                errors.Add("godot_bin_env.env_var_value must be an absolute path");
            }

            var envVarScope = godotBinEnv.TryGetProperty("env_var_scope", out var envVarScopeElement)
                ? envVarScopeElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(envVarScope) ||
                !(string.Equals(envVarScope, "Process", StringComparison.OrdinalIgnoreCase)
                  || string.Equals(envVarScope, "User", StringComparison.OrdinalIgnoreCase)
                  || string.Equals(envVarScope, "Machine", StringComparison.OrdinalIgnoreCase)))
            {
                errors.Add("godot_bin_env.env_var_scope must be one of Process/User/Machine");
            }

            var envEvidencePath = godotBinEnv.TryGetProperty("evidence_file", out var envEvidenceFileElement)
                ? envEvidenceFileElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(envEvidencePath))
            {
                errors.Add("godot_bin_env.evidence_file is required");
            }
            else
            {
                var envEvidenceAbsolutePath = Path.Combine(repoRoot, envEvidencePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
                if (!File.Exists(envEvidenceAbsolutePath))
                {
                    errors.Add($"godot_bin_env.evidence_file does not exist: {envEvidencePath}");
                }
            }
        }

        if (!root.TryGetProperty("windows_only_check", out var windowsOnly) || windowsOnly.ValueKind != JsonValueKind.Object)
        {
            errors.Add("missing windows_only_check object");
        }
        else if (!windowsOnly.TryGetProperty("result", out var windowsOnlyResult))
        {
            errors.Add("missing windows_only_check.result");
        }
        else if (!string.Equals(windowsOnlyResult.GetString(), "pass", StringComparison.OrdinalIgnoreCase))
        {
            errors.Add("windows_only_check.result must be pass");
        }

        if (!root.TryGetProperty("os_platform", out var osPlatform) ||
            !string.Equals(osPlatform.GetString(), "Windows", StringComparison.OrdinalIgnoreCase))
        {
            errors.Add("os_platform must be Windows");
        }

        if (!root.TryGetProperty("godot_bin_check", out var godotBinCheck) || godotBinCheck.ValueKind != JsonValueKind.Object)
        {
            errors.Add("missing godot_bin_check object");
        }
        else
        {
            var absolutePath = godotBinCheck.TryGetProperty("absolute_path", out var absolutePathElement)
                ? absolutePathElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(absolutePath) || !Path.IsPathRooted(absolutePath))
            {
                errors.Add("godot_bin_check.absolute_path must be an absolute path");
            }

            var installResult = godotBinCheck.TryGetProperty("installation_verification_result", out var installResultElement)
                ? installResultElement.GetString()
                : null;
            if (!string.Equals(installResult, "pass", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(installResult, "fail", StringComparison.OrdinalIgnoreCase))
            {
                errors.Add("godot_bin_check.installation_verification_result must be pass or fail");
            }

            if (godotBinCheck.TryGetProperty("is_absolute", out var isAbsoluteElement)
                && isAbsoluteElement.ValueKind == JsonValueKind.True
                && !Path.IsPathRooted(absolutePath))
            {
                errors.Add("godot_bin_check.is_absolute is true but absolute_path is not rooted");
            }
        }

        if (!root.TryGetProperty("utf8_check", out var utf8Check) || utf8Check.ValueKind != JsonValueKind.Object)
        {
            errors.Add("missing utf8_check object");
        }
        else if (!utf8Check.TryGetProperty("result", out var utf8Result))
        {
            errors.Add("missing utf8_check.result");
        }
        else if (!string.Equals(utf8Result.GetString(), "pass", StringComparison.OrdinalIgnoreCase))
        {
            errors.Add("utf8_check.result must be pass");
        }
        else
        {
            var utf8EvidencePath = utf8Check.TryGetProperty("evidence_file", out var utf8EvidenceFileElement)
                ? utf8EvidenceFileElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(utf8EvidencePath))
            {
                errors.Add("utf8_check.evidence_file is required");
            }
            else
            {
                var utf8EvidenceAbsolutePath = Path.Combine(repoRoot, utf8EvidencePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
                if (!File.Exists(utf8EvidenceAbsolutePath))
                {
                    errors.Add($"utf8_check.evidence_file does not exist: {utf8EvidencePath}");
                }
            }
        }

        if (!root.TryGetProperty("evidence_paths", out var evidencePaths) || evidencePaths.ValueKind != JsonValueKind.Array)
        {
            errors.Add("missing evidence_paths array");
            return ValidationResult.Fail(errors);
        }

        if (!root.TryGetProperty("dotnet_sdk_check", out var sdkCheck) || sdkCheck.ValueKind != JsonValueKind.Object)
        {
            errors.Add("missing dotnet_sdk_check object");
        }
        else
        {
            var sdkExitCode = sdkCheck.TryGetProperty("exit_code", out var sdkExitCodeElement)
                ? sdkExitCodeElement.GetInt32()
                : -1;
            if (sdkExitCode != 0)
            {
                errors.Add("dotnet_sdk_check.exit_code must be 0");
            }

            var hasDotnet8Sdk = sdkCheck.TryGetProperty("has_dotnet8_sdk", out var hasDotnet8Element)
                && hasDotnet8Element.ValueKind == JsonValueKind.True;
            if (!hasDotnet8Sdk)
            {
                errors.Add("dotnet_sdk_check.has_dotnet8_sdk must be true");
            }

            var sdkEvidencePath = sdkCheck.TryGetProperty("evidence_file", out var sdkEvidenceFileElement)
                ? sdkEvidenceFileElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(sdkEvidencePath))
            {
                errors.Add("dotnet_sdk_check.evidence_file is required");
            }
            else
            {
                var sdkEvidenceAbsolutePath = Path.Combine(repoRoot, sdkEvidencePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
                if (!File.Exists(sdkEvidenceAbsolutePath))
                {
                    errors.Add($"dotnet_sdk_check.evidence_file does not exist: {sdkEvidencePath}");
                }
            }
        }

        var expectedEvidencePaths = RequiredEvidenceFiles
            .Select(file => $"logs/ci/{dateSegment}/env-evidence/{file}")
            .ToArray();
        var requiredDirectories = new[]
        {
            Path.Combine(repoRoot, "logs"),
            Path.Combine(repoRoot, "logs", "ci"),
            Path.Combine(repoRoot, "logs", "ci", dateSegment),
            Path.Combine(repoRoot, "logs", "ci", dateSegment, "env-evidence"),
        };
        foreach (var requiredDirectory in requiredDirectories)
        {
            if (!Directory.Exists(requiredDirectory))
            {
                errors.Add($"missing required directory: {requiredDirectory}");
            }
        }

        var actual = evidencePaths
            .EnumerateArray()
            .Select(item => item.GetString())
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .Cast<string>()
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (var expectedPath in expectedEvidencePaths)
        {
            if (!actual.Contains(expectedPath))
            {
                errors.Add($"missing evidence_paths entry: {expectedPath}");
                continue;
            }

            var absolutePath = Path.Combine(repoRoot, expectedPath.Replace("/", Path.DirectorySeparatorChar.ToString()));
            if (!File.Exists(absolutePath))
            {
                errors.Add($"missing evidence file: {expectedPath}");
            }
        }

        if (root.TryGetProperty("windows_only_check", out windowsOnly) && windowsOnly.ValueKind == JsonValueKind.Object)
        {
            var windowsEvidencePath = windowsOnly.TryGetProperty("evidence_file", out var evidencePathElement)
                ? evidencePathElement.GetString()
                : null;
            if (string.IsNullOrWhiteSpace(windowsEvidencePath))
            {
                errors.Add("windows_only_check.evidence_file is required");
            }
            else
            {
                var windowsEvidenceAbsolutePath = Path.Combine(repoRoot, windowsEvidencePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
                if (!File.Exists(windowsEvidenceAbsolutePath))
                {
                    errors.Add($"windows_only_check.evidence_file does not exist: {windowsEvidencePath}");
                }

                var platformEvidence = windowsOnly.TryGetProperty("platform_evidence", out var platformEvidenceElement)
                    ? platformEvidenceElement.GetString()
                    : null;
                if (string.IsNullOrWhiteSpace(platformEvidence))
                {
                    errors.Add("windows_only_check.platform_evidence is required");
                }
                else if (File.Exists(windowsEvidenceAbsolutePath))
                {
                    var windowsEvidenceContent = File.ReadAllText(windowsEvidenceAbsolutePath);
                    if (!windowsEvidenceContent.Contains(platformEvidence, StringComparison.OrdinalIgnoreCase))
                    {
                        errors.Add("windows_only_check.evidence_file must include platform_evidence value");
                    }
                }
            }
        }

        return errors.Count == 0 ? ValidationResult.Pass() : ValidationResult.Fail(errors);
    }

    private static ValidationResult ValidateChecklistEvidencePaths(
        string checklistContent,
        string repoRoot,
        string dateSegment,
        IReadOnlyCollection<string> expectedEvidencePaths)
    {
        var sectionStart = checklistContent.IndexOf(Task1ChecklistSectionToken, StringComparison.OrdinalIgnoreCase);
        if (sectionStart < 0)
        {
            return ValidationResult.Fail(new[] { "task1 checklist section token is missing (ACC:T1.3)" });
        }

        var nextSectionStart = checklistContent.IndexOf(
            "\n## ",
            sectionStart + Task1ChecklistSectionToken.Length,
            StringComparison.Ordinal);
        var task1Section = nextSectionStart > sectionStart
            ? checklistContent[sectionStart..nextSectionStart]
            : checklistContent[sectionStart..];
        var refs = ChecklistPathRegex
            .Matches(task1Section)
            .Select(match => match.Value)
            .Where(Path.HasExtension)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        var errors = new List<string>();
        if (refs.Length == 0)
        {
            errors.Add("no logs/** evidence refs found in checklist");
            return ValidationResult.Fail(errors);
        }

        var expectedSet = expectedEvidencePaths
            .Select(path => path.Replace("\\", "/"))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var requiredPrefix = $"logs/ci/{dateSegment}/env-evidence/";
        var normalizedRefs = refs
            .Select(path => path.Replace(DateToken, dateSegment, StringComparison.OrdinalIgnoreCase))
            .Select(path => path.Replace("\\", "/"))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (var expectedPath in expectedSet)
        {
            if (!normalizedRefs.Contains(expectedPath))
            {
                errors.Add($"checklist missing task-0001 evidence path: {expectedPath}");
            }
        }

        foreach (var relativePath in normalizedRefs)
        {
            if (!relativePath.StartsWith(requiredPrefix, StringComparison.OrdinalIgnoreCase))
            {
                errors.Add($"env-evidence path must use current date prefix '{requiredPrefix}': {relativePath}");
                continue;
            }

            var absolutePath = Path.Combine(repoRoot, relativePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
            if (!File.Exists(absolutePath))
            {
                errors.Add($"checklist evidence path does not exist: {relativePath}");
            }
        }

        return errors.Count == 0 ? ValidationResult.Pass() : ValidationResult.Fail(errors);
    }

    private static ValidationResult ValidateAdrBacklinks(JsonElement taskRoot, string checklistContent)
    {
        var collected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        if (taskRoot.TryGetProperty("adr_refs", out var adrRefs) && adrRefs.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in adrRefs.EnumerateArray())
            {
                var value = item.GetString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    collected.Add(value);
                }
            }
        }

        foreach (Match match in AdrRegex.Matches(checklistContent))
        {
            collected.Add(match.Value);
        }

        var errors = RequiredAdrs
            .Where(required => !collected.Contains(required))
            .Select(required => $"missing required ADR backlink: {required}")
            .ToList();

        return errors.Count == 0 ? ValidationResult.Pass() : ValidationResult.Fail(errors);
    }

    private static ValidationResult ValidateUtf8Check(JsonElement taskRoot, string repoRoot)
    {
        var errors = new List<string>();

        if (!taskRoot.TryGetProperty("utf8_check", out var utf8Check) || utf8Check.ValueKind != JsonValueKind.Object)
        {
            errors.Add("missing utf8_check object");
            return ValidationResult.Fail(errors);
        }

        var result = utf8Check.TryGetProperty("result", out var resultElement) ? resultElement.GetString() : null;
        if (!string.Equals(result, "pass", StringComparison.OrdinalIgnoreCase))
        {
            errors.Add("utf8_check.result must be pass");
        }

        var evidencePath = utf8Check.TryGetProperty("evidence_file", out var evidenceFile) ? evidenceFile.GetString() : null;
        if (string.IsNullOrWhiteSpace(evidencePath))
        {
            errors.Add("utf8_check.evidence_file is required");
            return ValidationResult.Fail(errors);
        }

        if (!utf8Check.TryGetProperty("checked_files", out var checkedFilesElement) ||
            checkedFilesElement.ValueKind != JsonValueKind.Array ||
            checkedFilesElement.GetArrayLength() == 0)
        {
            errors.Add("utf8_check.checked_files must be a non-empty array");
            return ValidationResult.Fail(errors);
        }

        var absolutePath = Path.Combine(repoRoot, evidencePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
        if (!File.Exists(absolutePath))
        {
            errors.Add($"utf8 evidence file does not exist: {evidencePath}");
            return ValidationResult.Fail(errors);
        }

        try
        {
            ReadUtf8Strict(absolutePath);
        }
        catch (DecoderFallbackException ex)
        {
            errors.Add($"utf8 evidence file decode failed: {ex.Message}");
        }

        var checkedFiles = checkedFilesElement.EnumerateArray()
            .Select(item => item.GetString())
            .Where(path => !string.IsNullOrWhiteSpace(path))
            .Cast<string>()
            .ToList();
        if (checkedFiles.Count == 0)
        {
            errors.Add("utf8_check.checked_files must not be empty");
        }

        if (!checkedFiles.Any(path => path.EndsWith("task-0001.json", StringComparison.OrdinalIgnoreCase)))
        {
            errors.Add("utf8_check.checked_files must include task-0001.json");
        }

        if (!checkedFiles.Any(path => path.EndsWith("ACCEPTANCE_CHECKLIST.md", StringComparison.OrdinalIgnoreCase)))
        {
            errors.Add("utf8_check.checked_files must include ACCEPTANCE_CHECKLIST.md");
        }
        if (!checkedFiles.Any(path => string.Equals(path.Replace("\\", "/"), ChecklistRelativePath, StringComparison.OrdinalIgnoreCase)))
        {
            errors.Add("utf8_check.checked_files must include canonical overlay ACCEPTANCE_CHECKLIST.md path");
        }

        var expectedEnvEvidence = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (taskRoot.TryGetProperty("evidence_paths", out var evidencePathsElement) && evidencePathsElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var entry in evidencePathsElement.EnumerateArray())
            {
                var path = entry.GetString();
                if (string.IsNullOrWhiteSpace(path))
                {
                    continue;
                }

                var normalized = path.Replace("\\", "/");
                if (normalized.Contains("/env-evidence/", StringComparison.OrdinalIgnoreCase))
                {
                    expectedEnvEvidence.Add(normalized);
                }
            }
        }

        foreach (var expectedPath in expectedEnvEvidence)
        {
            if (expectedPath.EndsWith("/utf8-check.txt", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (!checkedFiles.Any(actual => string.Equals(actual.Replace("\\", "/"), expectedPath, StringComparison.OrdinalIgnoreCase)))
            {
                errors.Add($"utf8_check.checked_files missing required env evidence path: {expectedPath}");
            }
        }

        var checklistAbsolutePath = Path.Combine(repoRoot, ChecklistRelativePath.Replace("/", Path.DirectorySeparatorChar.ToString()));
        if (!File.Exists(checklistAbsolutePath))
        {
            errors.Add($"canonical checklist file does not exist: {ChecklistRelativePath}");
        }
        else
        {
            try
            {
                var checklistContent = ReadUtf8Strict(checklistAbsolutePath);
                foreach (var anchor in ChecklistSemanticAnchors)
                {
                    if (!checklistContent.Contains(anchor, StringComparison.Ordinal))
                    {
                        errors.Add($"checklist semantic anchor missing: {anchor}");
                    }
                }

                foreach (var marker in ChecklistMojibakeMarkers)
                {
                    if (checklistContent.Contains(marker, StringComparison.Ordinal))
                    {
                        errors.Add($"checklist appears mojibake-corrupted: contains marker '{marker}'");
                    }
                }
            }
            catch (DecoderFallbackException ex)
            {
                errors.Add($"canonical checklist utf8 decode failed: {ex.Message}");
            }
        }

        foreach (var checkedFile in checkedFiles)
        {
            var checkedAbsolutePath = Path.Combine(repoRoot, checkedFile.Replace("/", Path.DirectorySeparatorChar.ToString()));
            if (!File.Exists(checkedAbsolutePath))
            {
                errors.Add($"utf8 checked file does not exist: {checkedFile}");
                continue;
            }

            try
            {
                ReadUtf8Strict(checkedAbsolutePath);
            }
            catch (DecoderFallbackException ex)
            {
                errors.Add($"utf8 checked file decode failed: {checkedFile}: {ex.Message}");
            }
        }

        return errors.Count == 0 ? ValidationResult.Pass() : ValidationResult.Fail(errors);
    }

    private static string ReadUtf8Strict(string path)
    {
        var bytes = File.ReadAllBytes(path);
        var utf8 = new UTF8Encoding(false, true);
        return utf8.GetString(bytes);
    }

    private static async Task<CommandResult> RunProcessAsync(string fileName, string arguments, string? prependPath = null)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
            };

            if (!string.IsNullOrWhiteSpace(prependPath))
            {
                var currentPath = Environment.GetEnvironmentVariable("PATH") ?? string.Empty;
                startInfo.Environment["PATH"] = prependPath + ";" + currentPath;
            }

            using var process = Process.Start(startInfo);
            if (process is null)
            {
                return new CommandResult(-1, string.Empty, string.Empty, "Process.Start returned null.");
            }

            var stdOutTask = process.StandardOutput.ReadToEndAsync();
            var stdErrTask = process.StandardError.ReadToEndAsync();

            using var timeoutCts = new CancellationTokenSource(CommandTimeout);
            try
            {
                await process.WaitForExitAsync(timeoutCts.Token);
            }
            catch (OperationCanceledException)
            {
                try
                {
                    if (!process.HasExited)
                    {
                        process.Kill(entireProcessTree: true);
                    }
                }
                catch
                {
                }

                var timeoutOut = await stdOutTask;
                var timeoutErr = await stdErrTask;
                return new CommandResult(-1, timeoutOut, timeoutErr, "Command timeout");
            }

            return new CommandResult(process.ExitCode, await stdOutTask, await stdErrTask, string.Empty);
        }
        catch (Exception ex)
        {
            return new CommandResult(-1, string.Empty, string.Empty, ex.Message);
        }
    }

    private static string BuildCombinedOutput(CommandResult result)
    {
        if (string.IsNullOrEmpty(result.StdErr))
        {
            return result.StdOut;
        }

        return result.StdOut + Environment.NewLine + result.StdErr;
    }

    private static string NormalizeLineEndings(string value)
    {
        return value.Replace("\r\n", "\n", StringComparison.Ordinal);
    }

    private static string FindRepoRoot()
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

    private static void RemoveJsonPath(JsonObject root, string path)
    {
        var parts = path.Split('.', StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0)
        {
            return;
        }

        JsonObject? current = root;
        for (var index = 0; index < parts.Length - 1; index++)
        {
            if (current is null || current[parts[index]] is not JsonObject next)
            {
                return;
            }

            current = next;
        }

        current?.Remove(parts[^1]);
    }

    private sealed record Task0001Artifact(
        string RepoRoot,
        string DateSegment,
        string TaskJsonPath,
        string EvidenceDirectory,
        string TaskJsonText);

    private sealed record ValidationResult(bool IsValid, IReadOnlyList<string> Errors)
    {
        public static ValidationResult Pass() => new(true, Array.Empty<string>());
        public static ValidationResult Fail(IEnumerable<string> errors) => new(false, errors.ToArray());
    }

    private sealed record CommandResult(int ExitCode, string StdOut, string StdErr, string Error);
}
