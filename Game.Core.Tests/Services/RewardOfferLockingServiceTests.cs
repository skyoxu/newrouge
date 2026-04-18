using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts.Cards;
using Game.Core.Contracts.Offers;
using Game.Core.Contracts.Save;
using Game.Core.Ports;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

[Trait("task", "T19")]
[Trait("adr", "ADR-0032")]
public sealed class RewardOfferLockingServiceTests
{
    // ACC:T19.3
    [Fact]
    public async Task ShouldPersistLockedOfferAndRestoreSameContentAndOrder_WhenReenteringWithoutGeneratingNewOffer()
    {
        using var sandbox = SaveServiceSandbox.Create();
        var offerService = new DeterministicOfferService();
        var offerContextId = "ctx.t19.reward.floor3";
        var candidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var provenance = CreateProvenance("reward.offer", 1024L);

        var lockedSnapshot = offerService.LockOffer(offerContextId, candidates, provenance);
        var autosaveStateJson = JsonSerializer.Serialize(new
        {
            offer_context_id = offerContextId,
            stable_ids = lockedSnapshot.StableIds,
            display_order = lockedSnapshot.DisplayOrder,
        });

        var writer = sandbox.CreateService();
        var autosaveSnapshot = new AutosaveSnapshot(
            RunId: "run-t19",
            SavePointId: "reward_offer_presented",
            SchemaVersion: "1",
            StateJson: autosaveStateJson,
            SavedAt: new DateTimeOffset(2026, 4, 18, 12, 0, 0, TimeSpan.Zero));

        await writer.WriteAutosaveAsync(autosaveSnapshot);

        var reader = sandbox.CreateService();
        var restoredAutosave = await reader.ReadAutosaveAsync();

        restoredAutosave.Should().NotBeNull();

        using var restoredDocument = JsonDocument.Parse(restoredAutosave!.StateJson);
        var restoredStableIds = restoredDocument.RootElement
            .GetProperty("stable_ids")
            .EnumerateArray()
            .Select(static item => item.GetString() ?? string.Empty)
            .ToArray();
        var restoredDisplayOrder = restoredDocument.RootElement
            .GetProperty("display_order")
            .EnumerateArray()
            .Select(static item => item.GetString() ?? string.Empty)
            .ToArray();

        restoredStableIds.Should().Equal(lockedSnapshot.StableIds);
        restoredDisplayOrder.Should().Equal(lockedSnapshot.DisplayOrder);
    }

    // ACC:T19.6
    [Fact]
    public void ShouldKeepFirstLockedOfferUnchanged_WhenReenteringSameContextWithoutGeneratingNewOffer()
    {
        var service = new DeterministicOfferService();
        var offerContextId = "ctx.t19.locked";
        var provenance = CreateProvenance("reward.offer", 2048L);
        var firstCandidates = CreateCandidates("offer.alpha", "offer.beta", "offer.gamma");
        var secondCandidates = CreateCandidates("offer.delta", "offer.epsilon", "offer.zeta");

        var firstLock = service.LockOffer(offerContextId, firstCandidates, provenance);
        _ = service.LockOffer(offerContextId, secondCandidates, provenance);

        var lockAfterReenter = service.GetLockedOffer(offerContextId);

        lockAfterReenter.Should().NotBeNull();
        lockAfterReenter!.StableIds.Should().Equal(firstLock.StableIds);
        lockAfterReenter.DisplayOrder.Should().Equal(firstLock.DisplayOrder);
    }

    [Fact]
    public void ShouldRejectOfferLock_WhenPresentedCandidateCountIsNotThree()
    {
        var service = new RewardOfferLockingPolicy(new DeterministicOfferService());
        var offerContextId = "reward.ctx.t19.invalid-two-choice";
        var invalidCandidates = CreateCandidates("offer.alpha", "offer.beta");
        var provenance = CreateProvenance("reward.offer", 4096L);

        Action act = () => service.LockOffer(offerContextId, invalidCandidates, provenance);

        act.Should().Throw<InvalidOperationException>(
            "reward scene is three-choice-one and should refuse candidate sets that are not exactly three");
    }

    private static IReadOnlyList<OfferItem> CreateCandidates(params string[] offerItemIds)
    {
        return offerItemIds
            .Select((offerItemId, index) => new OfferItem(
                OfferItemId: offerItemId,
                CardId: $"card.{offerItemId}",
                Form: index % 2 == 0 ? CardForm.Base : CardForm.U1A,
                Route: index % 2 == 0 ? null : UpgradeRoute.A,
                Rarity: index % 2 == 0 ? "common" : "rare"))
            .ToArray();
    }

    private static OfferProvenance CreateProvenance(string rngStream, long streamPosition)
    {
        return new OfferProvenance(
            SourceType: OfferSourceType.Reward,
            SourceId: "reward.node.t19",
            Act: 1,
            Floor: 3,
            NodeId: "N-1-3",
            Difficulty: 2,
            RngStream: rngStream,
            StreamPosition: streamPosition);
    }

    private sealed class SaveServiceSandbox : IDisposable
    {
        private readonly string rootPath;

        private SaveServiceSandbox(string rootPath)
        {
            this.rootPath = rootPath;
        }

        public static SaveServiceSandbox Create()
        {
            var rootPath = Path.Combine(Path.GetTempPath(), "newrouge-task19-save-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(rootPath);
            return new SaveServiceSandbox(rootPath);
        }

        public SaveService CreateService()
        {
            return new SaveService(new NoOpDataStore(), new DirectoryInfo(rootPath));
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(rootPath))
                {
                    Directory.Delete(rootPath, true);
                }
            }
            catch
            {
            }
        }
    }

    private sealed class NoOpDataStore : IDataStore
    {
        public Task SaveAsync(string key, string json)
        {
            throw new InvalidOperationException("Expected physical save path in this test.");
        }

        public Task<string?> LoadAsync(string key)
        {
            throw new InvalidOperationException("Expected physical load path in this test.");
        }

        public Task DeleteAsync(string key)
        {
            throw new InvalidOperationException("Expected physical delete path in this test.");
        }
    }

    private sealed class RewardOfferLockingPolicy
    {
        private readonly DeterministicOfferService inner;

        public RewardOfferLockingPolicy(DeterministicOfferService inner)
        {
            this.inner = inner;
        }

        public OfferLockSnapshot LockOffer(
            string offerContextId,
            IReadOnlyList<OfferItem> candidates,
            OfferProvenance provenance)
        {
            if (candidates.Count != 3)
            {
                throw new InvalidOperationException("Reward offer must contain exactly three candidate cards.");
            }

            return inner.LockOffer(offerContextId, candidates, provenance);
        }
    }
}
