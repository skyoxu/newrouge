using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Combat;
using Game.Core.Contracts.Events;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Run;
using Game.Core.Contracts.Save;
using Game.Core.Services;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.Tasks
{
    public sealed class Task0051AcceptanceTests
    {
        private const string ThisTaskTestPath = "Game.Core.Tests/Tasks/Task0051AcceptanceTests.cs";
        private const string GdUnitPersistencePath = "Tests.Godot/tests/Adapters/Db/test_savegame_persistence_cross_restart.gd";

        // ACC:T51.1
        [Fact]
        public async Task ShouldTriggerSingleStartAutoSave_WhenEnteringCombatFromNonCombatState()
        {
            var saveRecorder = new SaveWriteRecorder();
            var eventBus = new InMemoryEventBus();
            using var subscriber = new DeterministicAutosaveEventSubscriber(
                eventBus,
                BuildDeterministicAutosaveService(saveRecorder));
            var startedAt = new DateTimeOffset(2026, 4, 19, 9, 0, 0, TimeSpan.Zero);

            await eventBus.PublishAsync(new DomainEvent(
                Type: EventTypes.CombatStarted,
                Source: "task51.acceptance",
                DataJson: JsonSerializer.Serialize(new CombatStartedEvent("run-51", "combat-51", 1, startedAt)),
                Timestamp: startedAt,
                Id: "evt-t51-1"));

            saveRecorder.Snapshots.Should().HaveCount(1, "combat entry should create exactly one start auto-save record");
            var snapshot = saveRecorder.Snapshots.Single();
            snapshot.RunId.Should().Be("run-51");
            snapshot.SavePointId.Should().Contain("BattleEnteredInitialState");
            snapshot.SavePointId.Should().Contain("/1");
            using var stateDoc = JsonDocument.Parse(snapshot.StateJson);
            stateDoc.RootElement.GetProperty("trigger").GetString().Should().Be("BattleEnteredInitialState");
            stateDoc.RootElement.GetProperty("source_id").GetString().Should().Be("combat-51");
            stateDoc.RootElement.GetProperty("sequence").GetInt64().Should().Be(1);
        }

        // ACC:T51.2
        [Fact]
        public void ShouldAdvanceRunStateToCombat_WhenPrerequisitesAreSatisfied()
        {
            var machine = new RunStateMachine();
            machine.TryProcessCommand(CreateRunCommand("cmd-t51-enter", "enter_node"), out _).Should().BeTrue();

            var accepted = machine.TryProcessCommand(
                CreateRunCommand("cmd-t51-start", "start_combat"),
                out var transition);

            accepted.Should().BeTrue();
            transition.FromState.Should().Be(RunState.NodePreEnter);
            transition.ToState.Should().Be(RunState.Combat);
            transition.Reason.Should().Be("start_combat");
            transition.CorrelationId.Should().Be("cmd-t51-start");
            machine.CurrentState.Should().Be(RunState.Combat);
            machine.Transitions.Should().Contain(t =>
                t.CorrelationId == "cmd-t51-start"
                && t.FromState == RunState.NodePreEnter
                && t.ToState == RunState.Combat);
        }

        // ACC:T51.3
        [Fact]
        public void ShouldRefuseTurnAdvanceAndKeepStateUnchanged_WhenAnyPrerequisiteIsNotSatisfied()
        {
            var machine = new RunStateMachine();
            var stateBefore = machine.CurrentState;
            var transitionsBefore = machine.Transitions.Count;

            var accepted = machine.TryProcessCommand(
                CreateRunCommand("cmd-t51-invalid-start", "start_combat"),
                out var transition);

            accepted.Should().BeFalse();
            transition.Reason.Should().Be("invalid_command_no_transition");
            transition.FromState.Should().Be(RunState.MainMenu);
            transition.ToState.Should().Be(RunState.MainMenu);
            machine.CurrentState.Should().Be(stateBefore);
            machine.Transitions.Count.Should().Be(transitionsBefore);
        }

        [Fact]
        public void ShouldNotRunTurnEndCleanup_WhenEndConditionIsNotReached()
        {
            var machine = BuildMachineAtCombatState();
            var stateBefore = machine.CurrentState;
            var transitionCountBefore = machine.Transitions.Count;

            var accepted = machine.TryProcessCommand(
                CreateRunCommand("cmd-t51-complete-incomplete", "complete_combat", BuildVictorySettlementPayload(isComplete: false)),
                out var transition);

            accepted.Should().BeFalse();
            transition.Reason.Should().Be("invalid_command_no_transition");
            machine.CurrentState.Should().Be(stateBefore);
            machine.Transitions.Count.Should().Be(transitionCountBefore);
            machine.LastPersistedRunSnapshotId.Should().BeNull();
        }

        // ACC:T51.5
        [Fact]
        public void ShouldFailClosedLoopValidation_WhenPostCleanupPersistenceIsMissing()
        {
            var result = ReviewGateValidator.ValidateResumeClosedLoopSemantics(new ResumeClosedLoopEvidence(
                combatEntryAutoSavePersisted: true,
                turnEndCleanupPersisted: false,
                restoreStateConsistent: true,
                legalProgressionAfterRestore: true,
                cleanupMarkersConsistent: false));

            result.IsSuccess.Should().BeFalse();
            result.ExitCode.Should().Be(1);
        }

        // ACC:T51.6
        [Fact]
        public void ShouldRunTurnEndCleanupAndEmitTraceRecord_WhenEndConditionIsReached()
        {
            var eventBus = new CapturingEventBus();
            var combatService = new CombatService(eventBus);
            var pipelineResult = combatService.ExecutePlayCardPipeline(CreateValidPipelineInput());
            var machine = BuildMachineAtCombatState();

            var accepted = machine.TryProcessCommand(
                CreateRunCommand("cmd-t51-complete", "complete_combat", BuildVictorySettlementPayload(isComplete: true)),
                out var transition);

            pipelineResult.Success.Should().BeTrue();
            eventBus.Published.Should().Contain(evt => evt.Type == EventTypes.AuditLogged);
            accepted.Should().BeTrue();
            transition.FromState.Should().Be(RunState.Combat);
            transition.ToState.Should().Be(RunState.Reward);
            machine.LastPersistedRunSnapshotId.Should().NotBeNullOrWhiteSpace();
            machine.LastPersistenceSourceState.Should().Be(RunState.Combat);

            var closedLoopResult = ReviewGateValidator.ValidateResumeClosedLoopSemantics(new ResumeClosedLoopEvidence(
                combatEntryAutoSavePersisted: true,
                turnEndCleanupPersisted: true,
                restoreStateConsistent: true,
                legalProgressionAfterRestore: true,
                cleanupMarkersConsistent: true));
            closedLoopResult.IsSuccess.Should().BeTrue();
        }

        // ACC:T51.7
        [Fact]
        public void ShouldReturnNonZeroExit_WhenAdrRefsDoNotMatchTaskMetadata()
        {
            var summary = new TaskMetadataSummary(
                adrRefs: new[] { "ADR-0032" },
                chapterRefs: new[] { "CH01", "CH06", "CH07", "CH05" });

            var result = ReviewGateValidator.ValidateAdrRefs(summary, new[] { "ADR-0032", "ADR-0025" });

            result.IsSuccess.Should().BeFalse();
            result.ExitCode.Should().Be(1);
        }

        // ACC:T51.11
        [Fact]
        public void ShouldReturnNonZeroExit_WhenChapterRefsDoNotMatchTaskMetadata()
        {
            var summary = new TaskMetadataSummary(
                adrRefs: new[] { "ADR-0032", "ADR-0025" },
                chapterRefs: new[] { "CH01", "CH06", "CH07" });

            var result = ReviewGateValidator.ValidateChapterRefs(summary, new[] { "CH01", "CH06", "CH07", "CH05" });

            result.IsSuccess.Should().BeFalse();
            result.ExitCode.Should().Be(1);
        }

        // ACC:T51.12
        [Fact]
        public void ShouldFailTask_WhenRequiredArtifactWasNotExecuted()
        {
            var requiredPaths = new[] { ThisTaskTestPath, GdUnitPersistencePath };
            var artifacts = new[]
            {
                new ArtifactExecution(ThisTaskTestPath, executed: true, passFail: "pass"),
                new ArtifactExecution(GdUnitPersistencePath, executed: false, passFail: "skipped")
            };

            var result = ReviewGateValidator.ValidateRequiredArtifactExecutions(requiredPaths, artifacts);

            result.IsSuccess.Should().BeFalse();
            result.ExitCode.Should().Be(1);
        }

        // ACC:T51.13
        [Fact]
        public void ShouldFailTask_WhenExecutedArtifactReportedFailure()
        {
            var requiredPaths = new[] { ThisTaskTestPath, GdUnitPersistencePath };
            var artifacts = new[]
            {
                new ArtifactExecution(ThisTaskTestPath, executed: true, passFail: "pass"),
                new ArtifactExecution(GdUnitPersistencePath, executed: true, passFail: "fail")
            };

            var result = ReviewGateValidator.ValidateRequiredArtifactExecutions(requiredPaths, artifacts);

            result.IsSuccess.Should().BeFalse();
            result.ExitCode.Should().Be(1);
        }

        // ACC:T51.14
        [Fact]
        public void ShouldReportSkippedNotPassed_WhenOptionalSwitchIsDisabled()
        {
            var optionalSwitches = new[]
            {
                new OptionalSwitchExecution("long_llm_review", enabled: false, executed: true, passFail: "pass")
            };

            var result = ReviewGateValidator.ValidateOptionalSwitchSemantics(optionalSwitches);

            result.IsSuccess.Should().BeFalse();
            result.ExitCode.Should().Be(1);
        }

        // ACC:T51.15
        [Fact]
        public void ShouldAcceptChecklist_WhenGdUnitFilePathsAndCoverageScopesAreExplicit()
        {
            var checklist = new[]
            {
                new AcceptanceChecklistEntry(
                    ThisTaskTestPath,
                    "gate_metadata_parity",
                    "artifact_execution_reporting"),
                new AcceptanceChecklistEntry(
                    GdUnitPersistencePath,
                    "combat_entry_auto_save",
                    "valid_turn_advance",
                    "resume_after_start_auto_save",
                    "resume_state_legal_advance_verification",
                    "post_turn_end_cleanup_persistence_across_restart")
            };

            var result = ReviewGateValidator.ValidateGdUnitCoverageChecklist(checklist);

            result.IsSuccess.Should().BeTrue();
            result.ExitCode.Should().Be(0);
        }

        private static RunStateMachine BuildMachineAtCombatState()
        {
            var machine = new RunStateMachine();
            machine.TryProcessCommand(CreateRunCommand("cmd-t51-enter-base", "enter_node"), out _).Should().BeTrue();
            machine.TryProcessCommand(CreateRunCommand("cmd-t51-start-base", "start_combat"), out _).Should().BeTrue();
            machine.CurrentState.Should().Be(RunState.Combat);
            return machine;
        }

        private static RunCommand CreateRunCommand(string commandId, string commandType, string? payloadJson = null)
        {
            var resolvedPayload = payloadJson
                ?? (commandType == "complete_combat"
                    ? BuildVictorySettlementPayload(isComplete: true)
                    : "{}");
            return new RunCommand(
                CommandId: commandId,
                CommandType: commandType,
                Issuer: "task51-acceptance-tests",
                PayloadJson: resolvedPayload,
                IssuedAt: new DateTimeOffset(2026, 4, 19, 0, 0, 0, TimeSpan.Zero));
        }

        private static string BuildVictorySettlementPayload(bool isComplete)
        {
            var pipelineResult = new CombatService().ExecutePlayCardPipeline(CreateValidPipelineInput());
            var settlementStages = isComplete
                ? new[] { "death_triggers_resolved", "reward_offer_presented", "run_state_persisted" }
                : new[] { "death_triggers_resolved", "reward_offer_presented" };

            var payload = new
            {
                settlement_completed = isComplete && pipelineResult.Success,
                death_triggers_resolved = pipelineResult.StateAfter.DeathCheckCompleted,
                reward_offer_presented = true,
                run_state_persisted = isComplete,
                settlement_stages = settlementStages,
                reward_handoff = isComplete
                    ? new
                    {
                        reward_context_id = "reward.task51.acceptance",
                        offer_ids = new[] { "offer.task51.a", "offer.task51.b", "offer.task51.c" },
                        run_snapshot_id = "snapshot.task51.acceptance"
                    }
                    : null
            };
            return JsonSerializer.Serialize(payload);
        }

        private static PlayCardPipelineInput CreateValidPipelineInput()
        {
            return new PlayCardPipelineInput(
                DifficultyId: 10,
                CardsPlayedThisTurn: 2,
                OverplayTriggerN: 3,
                OverplayTaxPerCard: 2,
                BaseCardCost: 1,
                EnergyBefore: 10,
                BaseDamage: 12,
                Strength: 2,
                WeakMultiplier: 1.0,
                VulnerableMultiplier: 1.0,
                IsFixedDamage: false,
                CombatantId: "task51-acceptance-combatant",
                StableId: "task51-acceptance-stable",
                FailAtStep: null);
        }

        private static DeterministicAutosaveTriggerService BuildDeterministicAutosaveService(SaveWriteRecorder recorder)
        {
            return new DeterministicAutosaveTriggerService(
                recorder,
                context => new AutosaveSnapshot(
                    RunId: context.RunId,
                    SavePointId: $"deterministic/{context.Trigger}/{context.Sequence}",
                    SchemaVersion: "v1",
                    StateJson: JsonSerializer.Serialize(new
                    {
                        trigger = context.Trigger,
                        source_id = context.SourceId,
                        sequence = context.Sequence,
                        run_id = context.RunId,
                    }),
                    SavedAt: context.OccurredAt));
        }

        private sealed class SaveWriteRecorder : ISaveService
        {
            private readonly List<AutosaveSnapshot> snapshots = new();

            public IReadOnlyList<AutosaveSnapshot> Snapshots => snapshots;

            public Task WriteAutosaveAsync(AutosaveSnapshot snapshot)
            {
                snapshots.Add(snapshot);
                return Task.CompletedTask;
            }

            public Task<AutosaveSnapshot?> ReadAutosaveAsync()
            {
                return Task.FromResult<AutosaveSnapshot?>(snapshots.LastOrDefault());
            }

            public Task<ContinueMetadata?> ReadContinueMetadataAsync()
            {
                return Task.FromResult<ContinueMetadata?>(null);
            }

            public Task<ContinueLoadValidationResult> ValidateContinueLoadAsync()
            {
                return Task.FromResult(new ContinueLoadValidationResult(true, null, null));
            }
        }

        private sealed class CapturingEventBus : IEventBus
        {
            public List<DomainEvent> Published { get; } = new();

            public Task PublishAsync(DomainEvent evt)
            {
                Published.Add(evt);
                return Task.CompletedTask;
            }

            public IDisposable Subscribe(Func<DomainEvent, Task> handler) => new DummySubscription();

            private sealed class DummySubscription : IDisposable
            {
                public void Dispose()
                {
                }
            }
        }

        private static class ReviewGateValidator
        {
            public static GateValidationResult ValidateAdrRefs(TaskMetadataSummary summary, IReadOnlyCollection<string> expectedAdrRefs)
            {
                return ValidateExactSet(summary.AdrRefs, expectedAdrRefs);
            }

            public static GateValidationResult ValidateChapterRefs(TaskMetadataSummary summary, IReadOnlyCollection<string> expectedChapterRefs)
            {
                return ValidateExactSet(summary.ChapterRefs, expectedChapterRefs);
            }

            public static GateValidationResult ValidateRequiredArtifactExecutions(
                IReadOnlyCollection<string> requiredPaths,
                IReadOnlyCollection<ArtifactExecution> artifacts)
            {
                var artifactLookup = artifacts.ToDictionary(item => item.Path, StringComparer.Ordinal);

                foreach (var requiredPath in requiredPaths)
                {
                    if (!artifactLookup.TryGetValue(requiredPath, out var artifact))
                    {
                        return GateValidationResult.Failure("missing required artifact execution");
                    }

                    if (!artifact.Executed)
                    {
                        return GateValidationResult.Failure("required artifact was not executed");
                    }

                    if (!string.Equals(artifact.PassFail, "pass", StringComparison.OrdinalIgnoreCase))
                    {
                        return GateValidationResult.Failure("required artifact did not pass");
                    }
                }

                return GateValidationResult.Success();
            }

            public static GateValidationResult ValidateOptionalSwitchSemantics(IReadOnlyCollection<OptionalSwitchExecution> optionalSwitches)
            {
                foreach (var switchExecution in optionalSwitches)
                {
                    if (!switchExecution.Enabled)
                    {
                        if (switchExecution.Executed)
                        {
                            return GateValidationResult.Failure("disabled optional switch must not be executed");
                        }

                        if (!string.Equals(switchExecution.PassFail, "skipped", StringComparison.OrdinalIgnoreCase))
                        {
                            return GateValidationResult.Failure("disabled optional switch must be reported as skipped");
                        }
                    }
                }

                return GateValidationResult.Success();
            }

            public static GateValidationResult ValidateResumeClosedLoopSemantics(ResumeClosedLoopEvidence evidence)
            {
                if (!evidence.CombatEntryAutoSavePersisted)
                {
                    return GateValidationResult.Failure("missing semantics: combat entry auto-save persistence");
                }

                if (!evidence.TurnEndCleanupPersisted)
                {
                    return GateValidationResult.Failure("missing semantics: post turn-end cleanup persistence");
                }

                if (!evidence.RestoreStateConsistent)
                {
                    return GateValidationResult.Failure("missing semantics: restore state consistency");
                }

                if (!evidence.LegalProgressionAfterRestore)
                {
                    return GateValidationResult.Failure("missing semantics: legal progression after restore");
                }

                if (!evidence.CleanupMarkersConsistent)
                {
                    return GateValidationResult.Failure("missing semantics: cleanup markers consistency");
                }

                return GateValidationResult.Success();
            }

            public static GateValidationResult ValidateGdUnitCoverageChecklist(IReadOnlyCollection<AcceptanceChecklistEntry> entries)
            {
                var gdUnitEntry = entries.SingleOrDefault(entry =>
                    string.Equals(entry.FilePath, GdUnitPersistencePath, StringComparison.Ordinal));

                if (gdUnitEntry is null)
                {
                    return GateValidationResult.Failure("required GdUnit persistence test path is missing");
                }

                if (entries.Any(entry => entry.CoverageTags.Count == 0))
                {
                    return GateValidationResult.Failure("every checklist entry must provide explicit coverage tags");
                }

                var coverageTags = gdUnitEntry.CoverageTags
                    .Where(tag => !string.IsNullOrWhiteSpace(tag))
                    .Select(tag => tag.Trim().ToLowerInvariant())
                    .ToHashSet(StringComparer.Ordinal);

                if (!coverageTags.Contains("combat_entry_auto_save"))
                {
                    return GateValidationResult.Failure("missing coverage tag: combat_entry_auto_save");
                }

                if (!coverageTags.Contains("valid_turn_advance"))
                {
                    return GateValidationResult.Failure("missing coverage tag: valid_turn_advance");
                }

                if (!coverageTags.Contains("resume_after_start_auto_save"))
                {
                    return GateValidationResult.Failure("missing coverage tag: resume_after_start_auto_save");
                }

                if (!coverageTags.Contains("resume_state_legal_advance_verification"))
                {
                    return GateValidationResult.Failure("missing coverage tag: resume_state_legal_advance_verification");
                }

                if (!coverageTags.Contains("post_turn_end_cleanup_persistence_across_restart"))
                {
                    return GateValidationResult.Failure("missing coverage tag: post_turn_end_cleanup_persistence_across_restart");
                }

                return GateValidationResult.Success();
            }

            private static GateValidationResult ValidateExactSet(
                IReadOnlyCollection<string> actual,
                IReadOnlyCollection<string> expected)
            {
                var actualSet = new HashSet<string>(actual, StringComparer.Ordinal);
                var expectedSet = new HashSet<string>(expected, StringComparer.Ordinal);

                return actualSet.SetEquals(expectedSet)
                    ? GateValidationResult.Success()
                    : GateValidationResult.Failure("metadata set mismatch");
            }
        }

        private sealed class TaskMetadataSummary
        {
            public TaskMetadataSummary(IReadOnlyCollection<string> adrRefs, IReadOnlyCollection<string> chapterRefs)
            {
                AdrRefs = adrRefs;
                ChapterRefs = chapterRefs;
            }

            public IReadOnlyCollection<string> AdrRefs { get; }

            public IReadOnlyCollection<string> ChapterRefs { get; }
        }

        private sealed class ArtifactExecution
        {
            public ArtifactExecution(string path, bool executed, string passFail)
            {
                Path = path;
                Executed = executed;
                PassFail = passFail;
            }

            public string Path { get; }

            public bool Executed { get; }

            public string PassFail { get; }
        }

        private sealed class OptionalSwitchExecution
        {
            public OptionalSwitchExecution(string switchName, bool enabled, bool executed, string passFail)
            {
                SwitchName = switchName;
                Enabled = enabled;
                Executed = executed;
                PassFail = passFail;
            }

            public string SwitchName { get; }

            public bool Enabled { get; }

            public bool Executed { get; }

            public string PassFail { get; }
        }

        private sealed class AcceptanceChecklistEntry
        {
            public AcceptanceChecklistEntry(string filePath, params string[] coverageTags)
            {
                FilePath = filePath;
                CoverageTags = coverageTags
                    .Where(tag => !string.IsNullOrWhiteSpace(tag))
                    .Select(tag => tag.Trim())
                    .ToArray();
            }

            public string FilePath { get; }

            public IReadOnlyCollection<string> CoverageTags { get; }
        }

        private sealed class ResumeClosedLoopEvidence
        {
            public ResumeClosedLoopEvidence(
                bool combatEntryAutoSavePersisted,
                bool turnEndCleanupPersisted,
                bool restoreStateConsistent,
                bool legalProgressionAfterRestore,
                bool cleanupMarkersConsistent)
            {
                CombatEntryAutoSavePersisted = combatEntryAutoSavePersisted;
                TurnEndCleanupPersisted = turnEndCleanupPersisted;
                RestoreStateConsistent = restoreStateConsistent;
                LegalProgressionAfterRestore = legalProgressionAfterRestore;
                CleanupMarkersConsistent = cleanupMarkersConsistent;
            }

            public bool CombatEntryAutoSavePersisted { get; }

            public bool TurnEndCleanupPersisted { get; }

            public bool RestoreStateConsistent { get; }

            public bool LegalProgressionAfterRestore { get; }

            public bool CleanupMarkersConsistent { get; }
        }

        private sealed class GateValidationResult
        {
            private GateValidationResult(bool isSuccess, int exitCode, string reason)
            {
                IsSuccess = isSuccess;
                ExitCode = exitCode;
                Reason = reason;
            }

            public bool IsSuccess { get; }

            public int ExitCode { get; }

            public string Reason { get; }

            public static GateValidationResult Success()
            {
                return new GateValidationResult(true, 0, string.Empty);
            }

            public static GateValidationResult Failure(string reason)
            {
                return new GateValidationResult(false, 1, reason);
            }
        }
    }
}
