using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Interfaces;
using Game.Core.Domain;
using Game.Core.Domain.ValueObjects;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public class CombatServiceTests
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

    [Fact]
    public void ShouldCalculateDamageAppliesResistanceAndCritical_WhenExecuted()
    {
        var cfg = new CombatConfig { CritMultiplier = 2.0 };
        cfg.Resistances[DamageType.Fire] = 0.5; // 50% resist

        var svc = new CombatService();
        var baseFire = new Damage(100, DamageType.Fire);
        var reduced = svc.CalculateDamage(baseFire, cfg);
        Assert.Equal(50, reduced);

        var crit = new Damage(100, DamageType.Fire, IsCritical: true);
        var reducedCrit = svc.CalculateDamage(crit, cfg);
        Assert.Equal(100, reducedCrit); // 100 * 0.5 * 2.0
    }

    [Fact]
    public void ShouldCalculateDamageWithArmorMitigatesLinearly_WhenExecuted()
    {
        var cfg = new CombatConfig();
        var svc = new CombatService();
        var dmg = new Damage(40, DamageType.Physical);
        var res = svc.CalculateDamage(dmg, cfg, armor: 10);
        Assert.Equal(30, res);
    }

    [Fact]
    public void ShouldApplyDamageReducesPlayerHealth_WhenExecuted()
    {
        var p = new Player(maxHealth: 100);
        var svc = new CombatService();
        svc.ApplyDamage(p, new Damage(25, DamageType.Physical));
        Assert.Equal(75, p.Health.Current);
    }

    [Fact]
    public void ShouldCalculateDamageWithoutResistanceOrCriticalReturnsEffectiveAmount_WhenExecuted()
    {
        var svc = new CombatService();
        var result = svc.CalculateDamage(new Damage(33, DamageType.Poison), CombatConfig.Default);

        result.Should().Be(33);
    }

    [Fact]
    public void ShouldCalculateDamageCriticalUsesMinimumMultiplierOfOne_WhenExecuted()
    {
        var cfg = new CombatConfig { CritMultiplier = 0.5 };
        var svc = new CombatService();

        var result = svc.CalculateDamage(new Damage(20, DamageType.Physical, IsCritical: true), cfg);

        result.Should().Be(20);
    }

    [Fact]
    public void ShouldCalculateDamageWithNegativeArmorTreatsArmorAsZero_WhenExecuted()
    {
        var svc = new CombatService();
        var cfg = CombatConfig.Default;

        var result = svc.CalculateDamage(new Damage(15, DamageType.Physical), cfg, armor: -10);

        result.Should().Be(15);
    }

    [Fact]
    public void ShouldApplyDamageWithConfigPublishesPlayerDamagedEvent_WhenExecuted()
    {
        var bus = new CapturingEventBus();
        var svc = new CombatService(bus);
        var player = new Player(maxHealth: 50);
        var cfg = CombatConfig.Default;

        svc.ApplyDamage(player, new Damage(7, DamageType.Physical), cfg);

        player.Health.Current.Should().Be(43);
        bus.Published.Should().ContainSingle();
        bus.Published[0].Type.Should().Be("player.damaged");
        bus.Published[0].Source.Should().Be(nameof(CombatService));
    }

    [Fact]
    public void ShouldApplyDamageEventPayloadShouldMatchCalculatedDamageAndFlags_WhenExecuted()
    {
        var bus = new CapturingEventBus();
        var svc = new CombatService(bus);
        var player = new Player(maxHealth: 100);
        var cfg = new CombatConfig { CritMultiplier = 2.0 };
        cfg.Resistances[DamageType.Fire] = 0.5;

        var damage = new Damage(Amount: 20, Type: DamageType.Fire, IsCritical: true);
        svc.ApplyDamage(player, damage, cfg);

        bus.Published.Should().ContainSingle();
        var evt = bus.Published[0];
        evt.Type.Should().Be("player.damaged");

        using var doc = JsonDocument.Parse(evt.DataJson);
        doc.RootElement.GetProperty("amount").GetInt32().Should().Be(20); // 20 * 0.5 * 2.0
        doc.RootElement.GetProperty("type").GetString().Should().Be(nameof(DamageType.Fire));
        doc.RootElement.GetProperty("critical").GetBoolean().Should().BeTrue();

        player.Health.Current.Should().Be(80);
    }

    [Fact]
    public void ShouldApplyDamagePlainAmountOverloadShouldNotPublishEvent_WhenExecuted()
    {
        var bus = new CapturingEventBus();
        var svc = new CombatService(bus);
        var player = new Player(maxHealth: 30);

        svc.ApplyDamage(player, amount: 5);

        player.Health.Current.Should().Be(25);
        bus.Published.Should().BeEmpty();
    }
}
