using System;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0004AcceptanceTests
{
    // ACC:T4.11
    [Fact]
    public void ShouldRejectUnknownRngStream_WhenLockingOffer()
    {
        var service = new DeterministicOfferService();
        var candidates = CreateCandidates();
        var provenance = CreateProvenance(rngStream: "invalid.stream");

        Action lockAction = () => service.LockOffer("ctx-invalid-stream", candidates, provenance);

        lockAction.Should().Throw<ArgumentException>()
            .WithMessage("*Unsupported rng_stream*");
    }

    // ACC:T4.12
    [Fact]
    public void ShouldRejectNegativeStreamPosition_WhenLockingOffer()
    {
        var service = new DeterministicOfferService();
        var candidates = CreateCandidates();
        var provenance = CreateProvenance(rngStream: "reward.offer", streamPosition: -1L);

        Action lockAction = () => service.LockOffer("ctx-invalid-position", candidates, provenance);

        lockAction.Should().Throw<ArgumentOutOfRangeException>()
            .WithMessage("*stream_pos must be non-negative*");
    }

    private static OfferProvenance CreateProvenance(string rngStream, long streamPosition = 64L)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.9",
            Act: 2,
            Floor: 9,
            NodeId: "N-2-9",
            Difficulty: 5,
            RngStream: rngStream,
            StreamPosition: streamPosition);
    }

    private static OfferItem[] CreateCandidates()
    {
        return new[]
        {
            new OfferItem("offer-a", "card.a", CardForm.Base, null, "common"),
            new OfferItem("offer-b", "card.b", CardForm.U1A, UpgradeRoute.A, "rare"),
        };
    }
}
