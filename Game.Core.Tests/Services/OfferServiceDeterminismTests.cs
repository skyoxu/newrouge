using System;
using System.Linq;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class OfferServiceDeterminismTests
{
    // ACC:T29.5
    [Fact]
    public void ShouldKeepOfferLockStableAndNotAdvanceProvenance_WhenLockingSameContextViaOfferService()
    {
        IOfferService service = new DeterministicOfferService();
        var candidates = CreateOfferCandidates();
        var provenance = CreateProvenance(streamPosition: 42);

        var firstSnapshot = service.LockOffer(
            offerContextId: "act1-normal-seed12345-pos42",
            candidates: candidates,
            provenance: provenance,
            isLockedAtSavePoint: true);
        var secondSnapshot = service.LockOffer(
            offerContextId: "act1-normal-seed12345-pos42",
            candidates: candidates,
            provenance: provenance,
            isLockedAtSavePoint: true);

        secondSnapshot.Should().BeSameAs(
            firstSnapshot,
            "re-locking the same context should reuse the deterministic lock rather than mutate state");
        secondSnapshot.StableIds.Should().Equal(firstSnapshot.StableIds);
        secondSnapshot.DisplayOrder.Should().Equal(firstSnapshot.DisplayOrder);
        secondSnapshot.Provenance.StreamPosition.Should().Be(
            provenance.StreamPosition,
            "offer locking should preserve the source RNG position for UI preview traceability");

        var fetchedSnapshot = service.GetLockedOffer("act1-normal-seed12345-pos42");
        fetchedSnapshot.Should().NotBeNull();
        fetchedSnapshot!.StableIds.Should().Equal(firstSnapshot.StableIds);
        fetchedSnapshot.Provenance.StreamPosition.Should().Be(provenance.StreamPosition);
    }

    // ACC:T29.5
    [Fact]
    public void ShouldKeepSelectionAndRngStateUnchanged_WhenPreviewingTwiceForSameSeedAndInput()
    {
        var service = new OfferPreviewService();
        const long streamPosition = 42;

        var firstPreview = service.PreviewSelection(
            act: 1,
            encounterType: "combat_normal",
            seed: 12345,
            streamPosition: streamPosition,
            pickCount: 3);

        var secondPreview = service.PreviewSelection(
            act: 1,
            encounterType: "combat_normal",
            seed: 12345,
            streamPosition: streamPosition,
            pickCount: 3);

        firstPreview.SelectedCardIds.Should().Equal(secondPreview.SelectedCardIds,
            "UI previews must return identical choices for the same seed and unchanged input state");
        firstPreview.StreamPositionAfterPreview.Should().Be(streamPosition,
            "UI preview must not advance RNG stream position");
        secondPreview.StreamPositionAfterPreview.Should().Be(streamPosition);
    }

    // ACC:T29.5
    [Fact]
    public void ShouldRefuseUnknownEncounterTypeWithoutChangingRngState_WhenPreviewingForUi()
    {
        var service = new OfferPreviewService();
        const long streamPosition = 7;
        const int seed = 99;

        var previewBeforeInvalidCall = service.PreviewSelection(
            act: 1,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        Action act = () => service.PreviewSelection(
            act: 1,
            encounterType: "raid",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        act.Should().Throw<ArgumentException>("unsupported encounter types must be refused");

        var previewAfterInvalidCall = service.PreviewSelection(
            act: 1,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        previewAfterInvalidCall.SelectedCardIds.Should().Equal(previewBeforeInvalidCall.SelectedCardIds,
            "a refused preview must not mutate deterministic selection state for the same input");
        previewAfterInvalidCall.StreamPositionAfterPreview.Should().Be(previewBeforeInvalidCall.StreamPositionAfterPreview,
            "a refused preview must not mutate external RNG position");
    }

    // ACC:T29.9
    [Fact]
    public void ShouldRefuseUnknownActWithoutChangingRngState_WhenPreviewingForUi()
    {
        var service = new OfferPreviewService();
        const long streamPosition = 11;
        const int seed = 2026;

        var previewBeforeInvalidCall = service.PreviewSelection(
            act: 2,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        Action act = () => service.PreviewSelection(
            act: 99,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        act.Should().Throw<ArgumentException>("unsupported acts must be rejected");

        var previewAfterInvalidCall = service.PreviewSelection(
            act: 2,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        previewAfterInvalidCall.SelectedCardIds.Should().Equal(previewBeforeInvalidCall.SelectedCardIds,
            "a refused act must not mutate deterministic preview selection");
        previewAfterInvalidCall.StreamPositionAfterPreview.Should().Be(previewBeforeInvalidCall.StreamPositionAfterPreview,
            "a refused act must not mutate external RNG position");
    }

    // ACC:T29.10
    [Fact]
    public void ShouldProduceDifferentSelections_WhenActOrEncounterChangesUnderSameSeedAndStream()
    {
        var service = new OfferPreviewService();
        const int seed = 512;
        const long streamPosition = 3;

        var act1Normal = service.PreviewSelection(
            act: 1,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);
        var act2Normal = service.PreviewSelection(
            act: 2,
            encounterType: "combat_normal",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);
        var act1Elite = service.PreviewSelection(
            act: 1,
            encounterType: "combat_elite",
            seed: seed,
            streamPosition: streamPosition,
            pickCount: 3);

        act1Normal.SelectedCardIds.Should().NotEqual(
            act2Normal.SelectedCardIds,
            "act should be part of the deterministic pool mapping");
        act1Normal.SelectedCardIds.Should().NotEqual(
            act1Elite.SelectedCardIds,
            "encounter type should be part of the deterministic pool mapping");
    }

    // ACC:T29.6
    [Fact]
    public void ShouldReturnSameRaritySequence_WhenSamplingWithSameActEncounterAndSeed()
    {
        var service = new OfferPreviewService();

        var firstRun = service.DrawRarities(act: 2, encounterType: "combat_normal", seed: 12345, drawCount: 64);
        var secondRun = service.DrawRarities(act: 2, encounterType: "combat_normal", seed: 12345, drawCount: 64);

        firstRun.Should().Equal(secondRun);
    }

    // ACC:T29.6
    [Fact]
    public void ShouldMatchStableGoldenRaritySequence_ForActEncounterSeedCombination()
    {
        var service = new OfferPreviewService();

        var rarities = service.DrawRarities(act: 2, encounterType: "combat_normal", seed: 12345, drawCount: 12);

        rarities.Should().Equal(
        [
            "uncommon",
            "common",
            "uncommon",
            "common",
            "uncommon",
            "common",
            "rare",
            "common",
            "common",
            "common",
            "uncommon",
            "common",
        ]);
    }

    // ACC:T29.6
    [Fact]
    public void ShouldMatchBossRarityDistribution_WhenSamplingLargeBatchFromBossPool()
    {
        var service = new OfferPreviewService();

        var rarities = service.DrawRarities(act: 3, encounterType: "boss", seed: 7, drawCount: 2000);
        var rareRatio = rarities.Count(rarity => rarity == "rare") / (double)rarities.Count;
        var uncommonRatio = rarities.Count(rarity => rarity == "uncommon") / (double)rarities.Count;
        var commonRatio = rarities.Count(rarity => rarity == "common") / (double)rarities.Count;

        rareRatio.Should().BeApproximately(0.35, 0.03);
        uncommonRatio.Should().BeApproximately(0.35, 0.03);
        commonRatio.Should().BeApproximately(0.30, 0.03);
    }

    private static OfferProvenance CreateProvenance(long streamPosition)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "node:act1/combat_normal",
            Act: 1,
            Floor: 2,
            NodeId: "act1_n2",
            Difficulty: 1,
            RngStream: RngStreamType.Offer,
            StreamPosition: streamPosition);
    }

    private static OfferItem[] CreateOfferCandidates()
    {
        return
        [
            new OfferItem(
                OfferItemId: "offer_001",
                CardId: "card_strike",
                Form: CardForm.Base,
                Route: null,
                Rarity: "common"),
            new OfferItem(
                OfferItemId: "offer_002",
                CardId: "card_defend",
                Form: CardForm.U1A,
                Route: UpgradeRoute.A,
                Rarity: "uncommon"),
            new OfferItem(
                OfferItemId: "offer_003",
                CardId: "card_bash",
                Form: CardForm.U1B,
                Route: UpgradeRoute.B,
                Rarity: "rare"),
        ];
    }
}
