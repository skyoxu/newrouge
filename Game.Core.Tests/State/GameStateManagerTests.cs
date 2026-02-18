using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using Game.Core.Contracts;
using Game.Core.Domain;
using Game.Core.Ports;
using Game.Core.State;
using Xunit;

namespace Game.Core.Tests.State;

internal sealed class InMemoryDataStore : IDataStore
{
    private readonly Dictionary<string,string> _dict = new();
    public Task SaveAsync(string key, string json) { _dict[key] = json; return Task.CompletedTask; }
    public Task<string?> LoadAsync(string key) { _dict.TryGetValue(key, out var v); return Task.FromResult(v); }
    public Task DeleteAsync(string key) { _dict.Remove(key); return Task.CompletedTask; }
    public IReadOnlyDictionary<string,string> Snapshot => _dict;
}

public class GameStateManagerTests
{
    private static GameState MakeState(int level=1, int score=0)
        => new(
            Id: Guid.NewGuid().ToString(),
            Level: level,
            Score: score,
            Health: 100,
            Inventory: Array.Empty<string>(),
            Position: new Game.Core.Domain.ValueObjects.Position(0,0),
            Timestamp: DateTime.UtcNow
        );

    private static GameConfig MakeConfig()
        => new(
            MaxLevel: 50,
            InitialHealth: 100,
            ScoreMultiplier: 1.0,
            AutoSave: false,
            Difficulty: Difficulty.Medium
        );

    [Fact]
    public async Task ShouldSaveLoadDeleteAndIndexFlowWorksWithCompression_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var opts = new GameStateManagerOptions(MaxSaves: 2, EnableCompression: true);
        var mgr = new GameStateManager(store, opts);

        var seen = new List<string>();
        mgr.OnEvent(e => seen.Add(e.Type));

        mgr.SetState(MakeState(level:2), MakeConfig());
        var id1 = await mgr.SaveGameAsync("slot1");
        Assert.Contains("game.save.created", seen);
        Assert.True(store.Snapshot.ContainsKey(id1));
        Assert.StartsWith("gz:", store.Snapshot[id1]);

        mgr.SetState(MakeState(level:3), MakeConfig());
        var id2 = await mgr.SaveGameAsync("slot2");
        var list = await mgr.GetSaveListAsync();
        Assert.True(list.Count >= 2);

        // Trigger cleanup by saving third; MaxSaves=2 => first gets deleted from store
        mgr.SetState(MakeState(level:4), MakeConfig());
        var id3 = await mgr.SaveGameAsync("slot3");

        var saveIndexKey = opts.StorageKey + ":index";
        var indexJson = await store.LoadAsync(saveIndexKey);
        Assert.NotNull(indexJson);
        var ids = JsonSerializer.Deserialize<List<string>>(indexJson!)!;
        Assert.Equal(2, ids.Count);
        Assert.DoesNotContain(id1, ids);

        // load latest
        var (state, cfg) = await mgr.LoadGameAsync(id3);
        Assert.Equal(4, state.Level);
        Assert.Equal(100, cfg.InitialHealth);

        // delete second
        await mgr.DeleteSaveAsync(id2);
        indexJson = await store.LoadAsync(saveIndexKey);
        ids = JsonSerializer.Deserialize<List<string>>(indexJson!)!;
        Assert.DoesNotContain(id2, ids);
    }

    [Fact]
    public async Task ShouldAutoSaveToggleAndTick_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);
        mgr.SetState(MakeState(level:5), MakeConfig());
        mgr.EnableAutoSave();
        await mgr.AutoSaveTickAsync();
        mgr.DisableAutoSave();
        var idx = await store.LoadAsync("guild-manager-game:index");
        Assert.NotNull(idx);
    }

    [Fact]
    public async Task ShouldSaveThrowsWhenStateMissingOrTitleTooLong_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);
        await Assert.ThrowsAsync<InvalidOperationException>(async () => await mgr.SaveGameAsync());

        mgr.SetState(MakeState(), MakeConfig());
        var tooLong = new string('x', 101);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(async () => await mgr.SaveGameAsync(tooLong));
    }

    [Fact]
    public async Task ShouldSaveThrowsWhenScreenshotExceedsLimit_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);

        mgr.SetState(MakeState(), MakeConfig());
        var tooLargeScreenshot = new string('x', 2_000_001);

        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(async () => await mgr.SaveGameAsync("slot", tooLargeScreenshot));
    }

    [Fact]
    public async Task ShouldLoadFailsWhenChecksumMismatch_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var opts = new GameStateManagerOptions(EnableCompression: false);
        var mgr = new GameStateManager(store, opts);

        mgr.SetState(MakeState(level: 9), MakeConfig());
        var saveId = await mgr.SaveGameAsync("slot");

        var raw = await store.LoadAsync(saveId);
        Assert.NotNull(raw);
        var save = JsonSerializer.Deserialize<SaveData>(raw!)!;
        var corrupted = save with
        {
            Metadata = save.Metadata with { Checksum = "BAD-CHECKSUM" }
        };

        await store.SaveAsync(saveId, JsonSerializer.Serialize(corrupted));

        await Assert.ThrowsAsync<InvalidOperationException>(async () => await mgr.LoadGameAsync(saveId));
    }

    [Fact]
    public async Task ShouldGetSaveListIgnoresBrokenEntriesInIndex_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var opts = new GameStateManagerOptions(EnableCompression: false);
        var mgr = new GameStateManager(store, opts);

        mgr.SetState(MakeState(level: 2), MakeConfig());
        var saveId = await mgr.SaveGameAsync("ok");

        var indexKey = opts.StorageKey + ":index";
        await store.SaveAsync(indexKey, JsonSerializer.Serialize(new[] { "missing-save", saveId }));

        var list = await mgr.GetSaveListAsync();

        Assert.Single(list);
        Assert.Equal(saveId, list[0].Id);
    }

    [Fact]
    public async Task ShouldGettersOffEventAndDestroyCoverNullAndResetPaths_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);

        Assert.Null(mgr.GetState());
        Assert.Null(mgr.GetConfig());

        var events = new List<DomainEvent>();
        Action<DomainEvent> onEvent = e => events.Add(e);
        mgr.OnEvent(onEvent);

        var state = MakeState(level: 6);
        var config = MakeConfig();
        mgr.SetState(state, config);

        Assert.NotNull(mgr.GetState());
        Assert.NotNull(mgr.GetConfig());
        Assert.NotSame(state, mgr.GetState());
        Assert.NotSame(config, mgr.GetConfig());

        mgr.OffEvent(onEvent);
        mgr.SetState(MakeState(level: 7), null);
        Assert.Single(events); // only first SetState published to callback

        mgr.EnableAutoSave();
        mgr.Destroy();

        Assert.Null(mgr.GetState());
        Assert.Null(mgr.GetConfig());

        // Destroy should clear autosave flag, so tick should be no-op and not throw.
        await mgr.AutoSaveTickAsync();
    }

    [Fact]
    public async Task ShouldAutoSaveEnableDisableAreIdempotentAndTickRespectsFlag_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);
        var events = new List<string>();
        mgr.OnEvent(e => events.Add(e.Type));

        mgr.SetState(MakeState(level: 8), MakeConfig());

        mgr.EnableAutoSave();
        mgr.EnableAutoSave(); // idempotent
        await mgr.AutoSaveTickAsync(); // should save and emit completed

        mgr.DisableAutoSave();
        mgr.DisableAutoSave(); // idempotent
        await mgr.AutoSaveTickAsync(); // disabled path: no-op

        Assert.Equal(1, events.FindAll(t => t == "game.autosave.enabled").Count);
        Assert.Equal(1, events.FindAll(t => t == "game.autosave.disabled").Count);
        Assert.Equal(1, events.FindAll(t => t == "game.autosave.completed").Count);
    }

    [Fact]
    public async Task ShouldSaveAndLoadEventsShouldIncludeExactSaveIdInPayload_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);
        var events = new List<DomainEvent>();
        mgr.OnEvent(events.Add);

        mgr.SetState(MakeState(level: 10), MakeConfig());
        var saveId = await mgr.SaveGameAsync("slot-payload");
        await mgr.LoadGameAsync(saveId);

        var created = events.FindLast(e => e.Type == "game.save.created");
        var loaded = events.FindLast(e => e.Type == "game.save.loaded");

        Assert.NotNull(created);
        Assert.NotNull(loaded);

        using (var createdDoc = JsonDocument.Parse(created!.DataJson))
        {
            var payloadSaveId = createdDoc.RootElement.GetProperty("saveId").GetString();
            Assert.Equal(saveId, payloadSaveId);
        }

        using (var loadedDoc = JsonDocument.Parse(loaded!.DataJson))
        {
            var payloadSaveId = loadedDoc.RootElement.GetProperty("saveId").GetString();
            Assert.Equal(saveId, payloadSaveId);
        }
    }

    [Fact]
    public void ShouldSetStateWithNullConfigShouldKeepPreviousConfig_WhenExecuted()
    {
        var store = new InMemoryDataStore();
        var mgr = new GameStateManager(store);

        var firstConfig = MakeConfig() with { Difficulty = Difficulty.Hard, ScoreMultiplier = 1.5 };
        mgr.SetState(MakeState(level: 1), firstConfig);
        mgr.SetState(MakeState(level: 2), config: null);

        var configAfterSecondSet = mgr.GetConfig();
        Assert.NotNull(configAfterSecondSet);
        Assert.Equal(firstConfig.Difficulty, configAfterSecondSet!.Difficulty);
        Assert.Equal(firstConfig.ScoreMultiplier, configAfterSecondSet.ScoreMultiplier);
    }
}

