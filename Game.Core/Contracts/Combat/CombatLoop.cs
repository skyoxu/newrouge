using System;
using System.Collections.Generic;
using System.Linq;

namespace Game.Core.Contracts.Combat;

/// <summary>
/// Represents the deterministic phase loop for one combat turn pipeline.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Feature-Slice-M1-Warrior.md
/// </remarks>
public sealed class CombatLoop
{
    private static readonly IReadOnlyDictionary<CombatLoopPhase, CombatLoopPhase> CanonicalNext =
        new Dictionary<CombatLoopPhase, CombatLoopPhase>
        {
            [CombatLoopPhase.StartOfTurn] = CombatLoopPhase.Draw,
            [CombatLoopPhase.Draw] = CombatLoopPhase.Main,
            [CombatLoopPhase.Main] = CombatLoopPhase.EndOfTurn,
            [CombatLoopPhase.EndOfTurn] = CombatLoopPhase.StartOfTurn,
        };

    /// <summary>
    /// Gets the current combat loop phase.
    /// </summary>
    public CombatLoopPhase CurrentPhase { get; private set; } = CombatLoopPhase.StartOfTurn;

    /// <summary>
    /// Gets the last guard rejection reason.
    /// </summary>
    public string? LastGuardFailureReason { get; private set; }

    /// <summary>
    /// Creates a combat loop at the default phase.
    /// </summary>
    public CombatLoop()
    {
    }

    /// <summary>
    /// Creates a combat loop at the provided phase.
    /// </summary>
    /// <param name="currentPhase">Initial phase value.</param>
    public CombatLoop(CombatLoopPhase currentPhase)
    {
        CurrentPhase = currentPhase;
    }

    /// <summary>
    /// Tries to transition the loop to target phase according to canonical order.
    /// </summary>
    /// <param name="targetPhase">Desired target phase.</param>
    /// <param name="guardReason">Guard rejection reason when transition is denied.</param>
    /// <returns>True when transition is accepted; otherwise false.</returns>
    public bool TryTransitionTo(CombatLoopPhase targetPhase, out string guardReason)
    {
        if (!CanonicalNext.TryGetValue(CurrentPhase, out var expectedNext))
        {
            guardReason = $"Unknown current phase: {CurrentPhase}.";
            LastGuardFailureReason = guardReason;
            return false;
        }

        if (expectedNext != targetPhase)
        {
            guardReason =
                $"Invalid combat loop transition: {CurrentPhase} -> {targetPhase}. Expected next phase: {expectedNext}.";
            LastGuardFailureReason = guardReason;
            return false;
        }

        CurrentPhase = targetPhase;
        LastGuardFailureReason = null;
        guardReason = string.Empty;
        return true;
    }
}

/// <summary>
/// Canonical deterministic combat loop phase order.
/// </summary>
public enum CombatLoopPhase
{
    StartOfTurn = 0,
    Draw = 1,
    Main = 2,
    EndOfTurn = 3,
}

/// <summary>
/// Canonical play-card pipeline steps.
/// </summary>
public enum PlayCardPipelineStep
{
    Validate = 0,
    ComputeCost = 1,
    PayCost = 2,
    BeforePlayTriggers = 3,
    ResolveEffect = 4,
    AfterPlayTriggers = 5,
    MoveCard = 6,
    DeathCheck = 7,
}

/// <summary>
/// Deterministic ordering key used by combat sequencing.
/// </summary>
/// <param name="CombatantId">Primary ordering key.</param>
/// <param name="StableId">Secondary ordering key.</param>
public sealed record CombatantOrderKey(string CombatantId, string StableId);

/// <summary>
/// Input contract for one PlayCard pipeline execution.
/// </summary>
public sealed record PlayCardPipelineInput(
    int DifficultyId,
    int CardsPlayedThisTurn,
    int OverplayTriggerN,
    int OverplayTaxPerCard,
    int BaseCardCost,
    int EnergyBefore,
    int BaseDamage,
    int Strength,
    double WeakMultiplier,
    double VulnerableMultiplier,
    bool IsFixedDamage,
    string CombatantId,
    string StableId,
    PlayCardPipelineStep? FailAtStep = null);

/// <summary>
/// Snapshot state for pipeline before/after comparison.
/// </summary>
public sealed record PlayCardPipelineState(
    int Energy,
    int FinalCost,
    int FinalDamage,
    int CardsPlayedThisTurn,
    int ResolvedEffects,
    bool CardMoved,
    bool DeathCheckCompleted);

/// <summary>
/// Deterministic result for one PlayCard execution.
/// </summary>
public sealed record PlayCardPipelineResult(
    bool Success,
    string? FailureReason,
    IReadOnlyList<PlayCardPipelineStep> ExecutedSteps,
    PlayCardPipelineState StateBefore,
    PlayCardPipelineState StateAfter,
    int OverplayTax,
    string OrderingKey,
    string ExecutionFingerprint);

/// <summary>
/// Pure-C# deterministic contract implementation for PlayCard resolution.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0021, ADR-0032.
/// </remarks>
public sealed class PlayCardResolutionPipeline
{
    private static readonly PlayCardPipelineStep[] CanonicalOrder =
    {
        PlayCardPipelineStep.Validate,
        PlayCardPipelineStep.ComputeCost,
        PlayCardPipelineStep.PayCost,
        PlayCardPipelineStep.BeforePlayTriggers,
        PlayCardPipelineStep.ResolveEffect,
        PlayCardPipelineStep.AfterPlayTriggers,
        PlayCardPipelineStep.MoveCard,
        PlayCardPipelineStep.DeathCheck,
    };

    /// <summary>
    /// Returns canonical step order.
    /// </summary>
    public static IReadOnlyList<PlayCardPipelineStep> StepOrder => CanonicalOrder;

    /// <summary>
    /// Sorts combatants deterministically by combatant_id then stable_id.
    /// </summary>
    public static IReadOnlyList<CombatantOrderKey> SortByDeterministicOrder(IEnumerable<CombatantOrderKey> items)
    {
        ArgumentNullException.ThrowIfNull(items);
        return items
            .OrderBy(static item => item.CombatantId, StringComparer.Ordinal)
            .ThenBy(static item => item.StableId, StringComparer.Ordinal)
            .ToArray();
    }

    /// <summary>
    /// Computes overplay tax. Enabled only when difficulty >= 10.
    /// </summary>
    public static int CalculateOverplayTax(
        int difficultyId,
        int cardsPlayedThisTurn,
        int overplayTriggerN,
        int overplayTaxPerCard)
    {
        if (difficultyId < 10)
        {
            return 0;
        }

        if (cardsPlayedThisTurn < overplayTriggerN)
        {
            return 0;
        }

        var triggerN = Math.Max(1, overplayTriggerN);
        var taxPerCard = Math.Max(0, overplayTaxPerCard);
        var overflowCount = cardsPlayedThisTurn - triggerN + 1;
        return Math.Max(0, overflowCount * taxPerCard);
    }

    /// <summary>
    /// Computes mutable damage with Strength/Weak/Vulnerable multipliers.
    /// Fixed damage is exempt from mutable multipliers.
    /// </summary>
    public static int CalculateDamageWithStatusMultipliers(
        int baseDamage,
        int strength,
        double weakMultiplier,
        double vulnerableMultiplier,
        bool isFixedDamage)
    {
        var normalizedBase = Math.Max(0, baseDamage);
        if (isFixedDamage)
        {
            return normalizedBase;
        }

        var mutable = Math.Max(0, normalizedBase + strength);
        var weak = Math.Max(0.0, weakMultiplier);
        var vulnerable = Math.Max(0.0, vulnerableMultiplier);
        var product = mutable * weak * vulnerable;
        return Math.Max(0, (int)Math.Round(product, MidpointRounding.AwayFromZero));
    }

    /// <summary>
    /// Executes one deterministic PlayCard pipeline run.
    /// </summary>
    public PlayCardPipelineResult Execute(PlayCardPipelineInput input)
    {
        ArgumentNullException.ThrowIfNull(input);

        var normalizedTrigger = Math.Max(1, input.OverplayTriggerN);
        var normalizedCardsPlayed = Math.Max(0, input.CardsPlayedThisTurn);
        var normalizedBaseCost = Math.Max(0, input.BaseCardCost);
        var normalizedEnergy = Math.Max(0, input.EnergyBefore);
        var orderingKey = $"{input.CombatantId}|{input.StableId}";
        var stateBefore = new PlayCardPipelineState(
            Energy: normalizedEnergy,
            FinalCost: 0,
            FinalDamage: 0,
            CardsPlayedThisTurn: normalizedCardsPlayed,
            ResolvedEffects: 0,
            CardMoved: false,
            DeathCheckCompleted: false);

        var executed = new List<PlayCardPipelineStep>(CanonicalOrder.Length);
        var workingEnergy = stateBefore.Energy;
        var finalCost = 0;
        var finalDamage = 0;
        var resolvedEffects = 0;
        var moved = false;
        var deathChecked = false;
        var overplayTax = 0;

        foreach (var step in CanonicalOrder)
        {
            executed.Add(step);

            if (input.FailAtStep == step)
            {
                return BuildFailure($"Injected failure at {step}.", executed, stateBefore, overplayTax, orderingKey);
            }

            switch (step)
            {
                case PlayCardPipelineStep.Validate:
                    if (string.IsNullOrWhiteSpace(input.CombatantId) || string.IsNullOrWhiteSpace(input.StableId))
                    {
                        return BuildFailure("Missing deterministic ordering keys.", executed, stateBefore, overplayTax, orderingKey);
                    }

                    if (input.BaseCardCost < 0 || input.EnergyBefore < 0)
                    {
                        return BuildFailure("Invalid negative cost or energy.", executed, stateBefore, overplayTax, orderingKey);
                    }

                    break;

                case PlayCardPipelineStep.ComputeCost:
                    overplayTax = CalculateOverplayTax(
                        difficultyId: input.DifficultyId,
                        cardsPlayedThisTurn: normalizedCardsPlayed,
                        overplayTriggerN: normalizedTrigger,
                        overplayTaxPerCard: input.OverplayTaxPerCard);
                    finalCost = normalizedBaseCost + overplayTax;
                    break;

                case PlayCardPipelineStep.PayCost:
                    if (workingEnergy < finalCost)
                    {
                        return BuildFailure("Insufficient energy after tax.", executed, stateBefore, overplayTax, orderingKey);
                    }

                    workingEnergy -= finalCost;
                    break;

                case PlayCardPipelineStep.BeforePlayTriggers:
                    break;

                case PlayCardPipelineStep.ResolveEffect:
                    finalDamage = CalculateDamageWithStatusMultipliers(
                        baseDamage: input.BaseDamage,
                        strength: input.Strength,
                        weakMultiplier: input.WeakMultiplier,
                        vulnerableMultiplier: input.VulnerableMultiplier,
                        isFixedDamage: input.IsFixedDamage);
                    resolvedEffects = 1;
                    break;

                case PlayCardPipelineStep.AfterPlayTriggers:
                    break;

                case PlayCardPipelineStep.MoveCard:
                    moved = true;
                    break;

                case PlayCardPipelineStep.DeathCheck:
                    deathChecked = true;
                    break;
            }
        }

        var stateAfter = new PlayCardPipelineState(
            Energy: workingEnergy,
            FinalCost: finalCost,
            FinalDamage: finalDamage,
            CardsPlayedThisTurn: normalizedCardsPlayed + 1,
            ResolvedEffects: resolvedEffects,
            CardMoved: moved,
            DeathCheckCompleted: deathChecked);
        var fingerprint = BuildFingerprint(success: true, executed, stateAfter, overplayTax, orderingKey);
        return new PlayCardPipelineResult(
            Success: true,
            FailureReason: null,
            ExecutedSteps: executed,
            StateBefore: stateBefore,
            StateAfter: stateAfter,
            OverplayTax: overplayTax,
            OrderingKey: orderingKey,
            ExecutionFingerprint: fingerprint);
    }

    private static PlayCardPipelineResult BuildFailure(
        string reason,
        IReadOnlyList<PlayCardPipelineStep> executed,
        PlayCardPipelineState stateBefore,
        int overplayTax,
        string orderingKey)
    {
        var fingerprint = BuildFingerprint(success: false, executed, stateBefore, overplayTax, orderingKey);
        return new PlayCardPipelineResult(
            Success: false,
            FailureReason: reason,
            ExecutedSteps: executed.ToArray(),
            StateBefore: stateBefore,
            StateAfter: stateBefore,
            OverplayTax: overplayTax,
            OrderingKey: orderingKey,
            ExecutionFingerprint: fingerprint);
    }

    private static string BuildFingerprint(
        bool success,
        IReadOnlyList<PlayCardPipelineStep> executed,
        PlayCardPipelineState state,
        int overplayTax,
        string orderingKey)
    {
        return string.Join(
            "|",
            orderingKey,
            success ? "ok" : "fail",
            overplayTax,
            state.Energy,
            state.FinalCost,
            state.FinalDamage,
            state.CardsPlayedThisTurn,
            string.Join(">", executed));
    }
}
