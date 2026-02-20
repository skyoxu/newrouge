using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Domain;
using Game.Core.Domain.ValueObjects;
using Game.Core.Engine;
using Xunit;

namespace Game.Core.Tests.Engine;

public class GameEngineCoreEventTests
{
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

    private static GameEngineCore CreateEngineAndBus(out CapturingEventBus bus)
    {
        var config = new GameConfig(
            MaxLevel: 10,
            InitialHealth: 100,
            ScoreMultiplier: 1.0,
            AutoSave: false,
            Difficulty: Difficulty.Medium
        );
        var inventory = new Inventory();
        bus = new CapturingEventBus();
        return new GameEngineCore(config, inventory, bus);
    }

    [Fact]
    public void ShouldStartPublishesGameStartedEvent_WhenExecuted()
    {
        // Arrange
        var engine = CreateEngineAndBus(out var bus);

        // Act
        engine.Start();

        // Assert
        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("game.started");
        evt.Source.Should().Be(nameof(GameEngineCore));
        evt.DataJson.Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public void ShouldAddScorePublishesScoreChangedEvent_WhenExecuted()
    {
        // Arrange
        var engine = CreateEngineAndBus(out var bus);
        engine.Start();
        bus.Published.Clear();

        // Act
        engine.AddScore(10);

        // Assert
        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("score.changed");
        evt.Source.Should().Be(nameof(GameEngineCore));
        evt.DataJson.Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public void ShouldApplyDamagePublishesPlayerHealthChangedEvent_WhenExecuted()
    {
        // Arrange
        var engine = CreateEngineAndBus(out var bus);
        engine.Start();
        bus.Published.Clear();

        // Act
        engine.ApplyDamage(new Damage(Amount: 10, Type: DamageType.Physical, IsCritical: false));

        // Assert
        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("player.health.changed");
        evt.Source.Should().Be(nameof(GameEngineCore));
        evt.DataJson.Should().NotBeNullOrWhiteSpace();
    }

    [Fact]
    public void ShouldMoveUpdatesPositionAndPublishesPlayerMovedEvent_WhenExecuted()
    {
        var engine = CreateEngineAndBus(out var bus);
        engine.Start();
        bus.Published.Clear();

        var next = engine.Move(3, 4);

        next.Position.X.Should().Be(3);
        next.Position.Y.Should().Be(4);
        bus.Published.Should().ContainSingle();
        bus.Published[0].Type.Should().Be("player.moved");
    }

    [Fact]
    public void ShouldEndReturnsResultAndPublishesGameEndedEvent_WhenExecuted()
    {
        var engine = CreateEngineAndBus(out var bus);
        engine.Start();
        engine.Move(1, 0);
        engine.AddScore(15);
        bus.Published.Clear();

        var result = engine.End();

        result.FinalScore.Should().BeGreaterThanOrEqualTo(0);
        result.PlayTimeSeconds.Should().BeGreaterThanOrEqualTo(0);
        bus.Published.Should().ContainSingle();
        bus.Published[0].Type.Should().Be("game.ended");
    }

    [Fact]
    public void ShouldAddScoreEventPayloadShouldIncludeAddedAndNewScore_WhenExecuted()
    {
        var engine = CreateEngineAndBus(out var bus);
        engine.Start();
        bus.Published.Clear();

        engine.AddScore(11);

        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("score.changed");
        evt.DataJson.Should().NotBeNullOrWhiteSpace();
        using var doc = JsonDocument.Parse(evt.DataJson!);
        doc.RootElement.GetProperty("added").GetInt32().Should().Be(11);
        doc.RootElement.GetProperty("score").GetInt32().Should().Be(11);
    }

    [Fact]
    public void ShouldApplyDamageEventPayloadShouldIncludeDeltaAndRemainingHealth_WhenExecuted()
    {
        var engine = CreateEngineAndBus(out var bus);
        engine.Start();
        bus.Published.Clear();

        var cfg = new CombatConfig();
        cfg.Resistances[DamageType.Fire] = 0.5;
        engine.ApplyDamage(new Damage(20, DamageType.Fire), cfg);

        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("player.health.changed");
        evt.DataJson.Should().NotBeNullOrWhiteSpace();
        using var doc = JsonDocument.Parse(evt.DataJson!);
        doc.RootElement.GetProperty("delta").GetInt32().Should().Be(-10);
        doc.RootElement.GetProperty("health").GetInt32().Should().Be(90);
    }

    [Fact]
    public void ShouldMethodsShouldNotThrowWhenEventBusIsNull_WhenExecuted()
    {
        var config = new GameConfig(10, 100, 1.0, false, Difficulty.Medium);
        var inventory = new Inventory();
        var engine = new GameEngineCore(config, inventory, bus: null, time: null);

        var started = engine.Start();
        var moved = engine.Move(1, 1);
        var damaged = engine.ApplyDamage(new Damage(5, DamageType.Physical));
        var scored = engine.AddScore(10);
        var ended = engine.End();

        started.Should().NotBeNull();
        moved.Should().NotBeNull();
        damaged.Should().NotBeNull();
        scored.Should().NotBeNull();
        ended.Should().NotBeNull();
    }
}
