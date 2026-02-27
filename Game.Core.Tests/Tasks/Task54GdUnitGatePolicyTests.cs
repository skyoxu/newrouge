using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public class Task54GdUnitGatePolicyTests
{
    // ACC:T54.4
    [Fact]
    public void ShouldFailOverallGate_WhenAnyAdaptersOrSecuritySuiteFails()
    {
        var results = new[]
        {
            new SuiteResult(SuiteKind.Adapters, Passed: true),
            new SuiteResult(SuiteKind.Security, Passed: false),
            new SuiteResult(SuiteKind.Integration, Passed: true),
            new SuiteResult(SuiteKind.Ui, Passed: true),
        };

        EvaluateOverallGate(results).Should().BeFalse();
    }

    [Fact]
    public void ShouldPassOverallGate_WhenOnlyIntegrationOrUiSuitesFail()
    {
        var results = new[]
        {
            new SuiteResult(SuiteKind.Adapters, Passed: true),
            new SuiteResult(SuiteKind.Security, Passed: true),
            new SuiteResult(SuiteKind.Integration, Passed: false),
            new SuiteResult(SuiteKind.Ui, Passed: false),
        };

        EvaluateOverallGate(results).Should().BeTrue();
    }

    // ACC:T54.3
    [Fact]
    public void ShouldClassifyHardAndSoftSuites_WhenUsingStablePolicy()
    {
        IsHardGate(SuiteKind.Adapters).Should().BeTrue();
        IsHardGate(SuiteKind.Security).Should().BeTrue();
        IsHardGate(SuiteKind.Integration).Should().BeFalse();
        IsHardGate(SuiteKind.Ui).Should().BeFalse();
    }

    // ACC:T54.10
    [Fact]
    public void ShouldIgnoreUnselectedHardSuites_WhenComputingOverallGateResult()
    {
        var selectedRuns = new[]
        {
            new SuiteResult(SuiteKind.Adapters, Passed: true, Selected: false),
            new SuiteResult(SuiteKind.Security, Passed: false, Selected: false),
            new SuiteResult(SuiteKind.Integration, Passed: true, Selected: true),
            new SuiteResult(SuiteKind.Ui, Passed: true, Selected: true),
        };

        EvaluateOverallGateSelectedOnly(selectedRuns).Should().BeTrue();
    }

    private static bool EvaluateOverallGate(IEnumerable<SuiteResult> results)
    {
        return results
            .Where(result => IsHardGate(result.Kind))
            .All(result => result.Passed);
    }

    private static bool EvaluateOverallGateSelectedOnly(IEnumerable<SuiteResult> results)
    {
        return results
            .Where(result => result.Selected)
            .Where(result => IsHardGate(result.Kind))
            .All(result => result.Passed);
    }

    private static bool IsHardGate(SuiteKind kind)
    {
        return kind is SuiteKind.Adapters or SuiteKind.Security;
    }

    private enum SuiteKind
    {
        Adapters,
        Security,
        Integration,
        Ui,
    }

    private readonly record struct SuiteResult(SuiteKind Kind, bool Passed, bool Selected = true);
}
