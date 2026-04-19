using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task51AdrTraceabilityGateTests
{
    [Fact]
    public void ShouldExposeExplicitAdr0032AndAdr0025MappingResults_WhenGateOutputIsEvaluated()
    {
        var gateOutput = new GateOutput(new[]
        {
            new AdrMappingResult("ADR-0032", true, "Game.Core.Tests/Services/CombatServiceTests.cs"),
            new AdrMappingResult("ADR-0025", true, "Game.Core.Tests/Contracts/RunAndSaveContractsTests.cs")
        });

        var evaluator = new AdrTraceabilityGateEvaluator();

        var result = evaluator.Evaluate(gateOutput);

        result.MappingStatus.Should().ContainKey("ADR-0032");
        result.MappingStatus.Should().ContainKey("ADR-0025");
        result.MappingStatus["ADR-0032"].Should().BeTrue();
        result.MappingStatus["ADR-0025"].Should().BeTrue();
    }

    // ACC:T51.10
    [Fact]
    public void ShouldFail_WhenAdr0032MappingIsMissingFromGateOutput()
    {
        var gateOutput = new GateOutput(new[]
        {
            new AdrMappingResult("ADR-0032", false, ""),
            new AdrMappingResult("ADR-0025", true, "Game.Core.Tests/Contracts/RunAndSaveContractsTests.cs")
        });

        var evaluator = new AdrTraceabilityGateEvaluator();

        var result = evaluator.Evaluate(gateOutput);

        result.MappingStatus["ADR-0032"].Should().BeFalse();
        result.IsPassed.Should().BeFalse("gate must fail when ADR-0032 mapping is missing");
    }

    [Fact]
    public void ShouldFail_WhenAdr0025MappingIsMissingFromGateOutput()
    {
        var gateOutput = new GateOutput(new[]
        {
            new AdrMappingResult("ADR-0032", true, "Game.Core.Tests/Services/CombatServiceTests.cs"),
            new AdrMappingResult("ADR-0025", false, "")
        });

        var evaluator = new AdrTraceabilityGateEvaluator();

        var result = evaluator.Evaluate(gateOutput);

        result.MappingStatus["ADR-0025"].Should().BeFalse();
        result.IsPassed.Should().BeFalse("gate must fail when ADR-0025 mapping is missing");
    }

    [Fact]
    public void ShouldPass_WhenBothRequiredAdrMappingsArePresent()
    {
        var gateOutput = new GateOutput(new[]
        {
            new AdrMappingResult("ADR-0032", true, "Game.Core.Tests/Services/CombatServiceTests.cs"),
            new AdrMappingResult("ADR-0025", true, "Game.Core.Tests/Contracts/RunAndSaveContractsTests.cs")
        });

        var evaluator = new AdrTraceabilityGateEvaluator();

        var result = evaluator.Evaluate(gateOutput);

        result.IsPassed.Should().BeTrue();
    }

    private sealed class AdrTraceabilityGateEvaluator
    {
        public GateEvaluation Evaluate(GateOutput gateOutput)
        {
            var requiredAdrIds = new[] { "ADR-0032", "ADR-0025" };
            var mappingStatus = requiredAdrIds.ToDictionary(
                adrId => adrId,
                adrId => gateOutput.MappingResults.Any(x => x.AdrId == adrId && x.Mapped));

            var isPassed = mappingStatus["ADR-0032"] && mappingStatus["ADR-0025"];

            return new GateEvaluation(isPassed, mappingStatus);
        }
    }

    private sealed record GateOutput(IReadOnlyList<AdrMappingResult> MappingResults);

    private sealed record AdrMappingResult(string AdrId, bool Mapped, string EvidencePath);

    private sealed record GateEvaluation(bool IsPassed, IReadOnlyDictionary<string, bool> MappingStatus);
}
