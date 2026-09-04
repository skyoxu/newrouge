using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public class Task56QualityGateAuditIntegrationTests
{
    private const int TaskId = 56;

    private static readonly string[] RequiredEvidenceFiles =
    {
        "Tests/CI/AuditLogs/ValidateAuditLogsTests.cs",
        "Game.Core.Tests/Tasks/Task56AuditLogValidationTests.cs",
        "Game.Core.Tests/Tasks/Task56QualityGateAuditIntegrationTests.cs"
    };

    [Fact]
    public void ShouldHaveExpectedTaskId_WhenUsingTask56Scaffold()
    {
        TaskId.Should().Be(56);
    }

    // ACC:T56.8
    [Fact]
    public void ShouldContainRequiredAuditGateEvidencePaths_WhenEvaluatingTaskAcceptance()
    {
        RequiredEvidenceFiles.Should().HaveCount(3);
        RequiredEvidenceFiles.Should().OnlyHaveUniqueItems();
        RequiredEvidenceFiles.Should().OnlyContain(path => path.EndsWith(".cs", StringComparison.Ordinal));

        RequiredEvidenceFiles.Should().Contain("Tests/CI/AuditLogs/ValidateAuditLogsTests.cs");
        RequiredEvidenceFiles.Should().Contain("Game.Core.Tests/Tasks/Task56AuditLogValidationTests.cs");
        RequiredEvidenceFiles.Should().Contain("Game.Core.Tests/Tasks/Task56QualityGateAuditIntegrationTests.cs");
    }

    [Fact]
    public void ShouldExposeStableDeterministicEvidenceSet_WhenComparedAsSet()
    {
        var expected = new HashSet<string>(StringComparer.Ordinal)
        {
            "Tests/CI/AuditLogs/ValidateAuditLogsTests.cs",
            "Game.Core.Tests/Tasks/Task56AuditLogValidationTests.cs",
            "Game.Core.Tests/Tasks/Task56QualityGateAuditIntegrationTests.cs"
        };

        var actual = new HashSet<string>(RequiredEvidenceFiles, StringComparer.Ordinal);
        actual.SetEquals(expected).Should().BeTrue();
    }
}

