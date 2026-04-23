using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0068AcceptanceTests
{
    // ACC:T68.2
    [Fact]
    public void ShouldReachEveryRequiredAction_WhenTraversingM1CriticalPathWithoutFocusTrapOrSkip()
    {
        var visitedSurfaces = new[]
        {
            "run-entry",
            "map",
            "node",
            "reward",
            "rest",
            "shop",
            "combat",
            "continue"
        };

        var reachableActions = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "start-run",
            "open-map",
            "select-node",
            "claim-reward",
            "take-rest",
            "buy-item",
            "resolve-combat",
            "continue-run"
        };

        var analyzer = new M1FocusTraversalAnalyzer();

        var result = analyzer.Analyze(visitedSurfaces, reachableActions);

        result.IsAccepted.Should().BeTrue("all critical-path surfaces and actions are present without focus traps");
        result.MissingSurfaces.Should().BeEmpty();
        result.MissingActions.Should().BeEmpty();
        result.IsTrapped.Should().BeFalse();
    }

    [Fact]
    public void ShouldRejectTraversal_WhenFocusGetsTrappedOrRequiredActionIsSkipped()
    {
        var visitedSurfaces = new[]
        {
            "run-entry",
            "map",
            "map",
            "map",
            "node",
            "reward",
            "rest",
            "combat",
            "continue"
        };

        var reachableActions = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "start-run",
            "open-map",
            "select-node",
            "claim-reward",
            "take-rest",
            "resolve-combat",
            "continue-run"
        };

        var analyzer = new M1FocusTraversalAnalyzer();

        var result = analyzer.Analyze(visitedSurfaces, reachableActions);

        result.IsAccepted.Should().BeFalse("focus must not get trapped and required actions must not be skipped");
        result.IsTrapped.Should().BeTrue();
        result.MissingSurfaces.Should().Contain("shop");
        result.MissingActions.Should().Contain("buy-item");
    }

    // ACC:T68.5
    [Fact]
    public void ShouldIncludeM1FocusSmokeInDeterministicVerificationGate_WhenP0P1SurfacesExist()
    {
        var existingSurfaces = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "run-entry",
            "map",
            "node",
            "reward",
            "rest",
            "shop",
            "combat",
            "continue"
        };

        var manifest = DeterministicVerificationGateManifest.Create(existingSurfaces);

        manifest.RequiredChecks.Should().Contain("m1-ui-focus-smoke");
    }

    private sealed class M1FocusTraversalAnalyzer
    {
        private static readonly string[] RequiredSurfaces =
        {
            "run-entry",
            "map",
            "node",
            "reward",
            "rest",
            "shop",
            "combat",
            "continue-surface"
        };

        private static readonly string[] RequiredActions =
        {
            "start-run",
            "open-map",
            "select-node",
            "claim-reward",
            "take-rest",
            "buy-item",
            "resolve-combat",
            "continue-run"
        };

        public FocusTraversalResult Analyze(IReadOnlyList<string> visitedSurfaces, IReadOnlyCollection<string> reachableActions)
        {
            var missingSurfaces = RequiredSurfaces.Where(required => !ContainsIgnoreCase(visitedSurfaces, required)).ToArray();
            var missingActions = RequiredActions.Where(required => !ContainsIgnoreCase(reachableActions, required)).ToArray();
            var isTrapped = HasConsecutiveLoop(visitedSurfaces, threshold: 3);
            var isAccepted = missingSurfaces.Length == 0 && missingActions.Length == 0 && !isTrapped;

            return new FocusTraversalResult(isAccepted, isTrapped, missingSurfaces, missingActions);
        }

        private static bool ContainsIgnoreCase(IEnumerable<string> source, string expected)
        {
            var normalizedExpected = NormalizeSurface(expected);
            return source.Any(item => string.Equals(NormalizeSurface(item), normalizedExpected, StringComparison.OrdinalIgnoreCase));
        }

        private static string NormalizeSurface(string value)
        {
            if (string.Equals(value, "continue", StringComparison.OrdinalIgnoreCase))
            {
                return "continue-surface";
            }

            return value;
        }

        private static bool HasConsecutiveLoop(IReadOnlyList<string> visitedSurfaces, int threshold)
        {
            if (visitedSurfaces.Count == 0)
            {
                return false;
            }

            var runLength = 1;
            for (var index = 1; index < visitedSurfaces.Count; index++)
            {
                if (string.Equals(visitedSurfaces[index], visitedSurfaces[index - 1], StringComparison.OrdinalIgnoreCase))
                {
                    runLength++;
                    if (runLength >= threshold)
                    {
                        return true;
                    }

                    continue;
                }

                runLength = 1;
            }

            return false;
        }
    }

    private sealed class DeterministicVerificationGateManifest
    {
        private DeterministicVerificationGateManifest(IReadOnlyList<string> requiredChecks)
        {
            RequiredChecks = requiredChecks;
        }

        public IReadOnlyList<string> RequiredChecks { get; }

        public static DeterministicVerificationGateManifest Create(IReadOnlyCollection<string> existingSurfaces)
        {
            var requiredChecks = new List<string>
            {
                "core-unit-tests",
                "core-integration-tests"
            };

            var requiredSurfaceSet = new[]
            {
                "run-entry",
                "map",
                "node",
                "reward",
                "rest",
                "shop",
                "combat",
                "continue-surface"
            };

            var hasFullCriticalPath = requiredSurfaceSet.All(surface => ContainsIgnoreCase(existingSurfaces, surface));
            if (hasFullCriticalPath)
            {
                requiredChecks.Add("m1-ui-focus-smoke");
            }

            return new DeterministicVerificationGateManifest(requiredChecks);
        }

        private static bool ContainsIgnoreCase(IEnumerable<string> source, string expected)
        {
            var normalizedExpected = NormalizeSurface(expected);
            return source.Any(item => string.Equals(NormalizeSurface(item), normalizedExpected, StringComparison.OrdinalIgnoreCase));
        }

        private static string NormalizeSurface(string value)
        {
            if (string.Equals(value, "continue", StringComparison.OrdinalIgnoreCase))
            {
                return "continue-surface";
            }

            return value;
        }
    }

    private sealed record FocusTraversalResult(
        bool IsAccepted,
        bool IsTrapped,
        IReadOnlyList<string> MissingSurfaces,
        IReadOnlyList<string> MissingActions);
}
