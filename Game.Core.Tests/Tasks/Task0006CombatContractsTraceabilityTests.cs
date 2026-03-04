using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Contracts;
using Game.Core.Contracts.Events;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0006CombatContractsTraceabilityTests
{
    private static readonly string[] RequiredAdrIds = new[] { "ADR-0021", "ADR-0032" };

    // ACC:T6.11
    [Fact]
    [Trait("task", "T6")]
    [Trait("adr", "ADR-0021")]
    [Trait("adr", "ADR-0032")]
    public void ShouldRequireBothAdr0021AndAdr0032_WhenCheckingTask0006Traceability()
    {
        var repoRoot = FindRepoRoot();

        var task6 = LoadTask6FromMaster(repoRoot);
        var masterAdrRefs = task6.GetProperty("adrRefs")
            .EnumerateArray()
            .Select(x => x.GetString())
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .ToArray();
        masterAdrRefs.Should().Contain(RequiredAdrIds);

        var overlayRelativePath = task6.GetProperty("overlay").GetString();
        overlayRelativePath.Should().NotBeNullOrWhiteSpace();
        var overlayPath = ResolveRepoPath(repoRoot, overlayRelativePath!);
        File.Exists(overlayPath).Should().BeTrue();
        var overlayText = File.ReadAllText(overlayPath);
        foreach (var adr in RequiredAdrIds)
        {
            overlayText.Should().Contain(adr);
        }

        ValidateViewAdrRefs(repoRoot, "tasks_back.json");
        ValidateViewAdrRefs(repoRoot, "tasks_gameplay.json");
    }

    [Fact]
    public void ShouldDefineCombatEventTypeConstants_WhenVerifyingExpectedValues()
    {
        EventTypes.CombatDamageResolved.Should().Be("core.combat.damage.resolved");
        EventTypes.CombatFixedDamageResolved.Should().Be("core.combat.fixed_damage.resolved");
        EventTypes.CombatLoopHardStopped.Should().Be("core.combat.loop.hard_stopped");
    }

    [Fact]
    public void ShouldMapCombatEventContracts_WhenUsingSharedEventTypeConstants()
    {
        CombatDamageResolvedEvent.EventType.Should().Be(EventTypes.CombatDamageResolved);
        CombatFixedDamageResolvedEvent.EventType.Should().Be(EventTypes.CombatFixedDamageResolved);
        CombatLoopHardStoppedEvent.EventType.Should().Be(EventTypes.CombatLoopHardStopped);
    }

    [Fact]
    public void ShouldExposeCloudEventLikeMembers_WhenInspectingDomainEventBase()
    {
        var domainEventType = typeof(DomainEvent);

        HasPublicMember(domainEventType, "Type").Should().BeTrue();
        HasPublicMember(domainEventType, "Source").Should().BeTrue();
        HasPublicMember(domainEventType, "DataJson").Should().BeTrue();
        HasPublicMember(domainEventType, "Timestamp").Should().BeTrue();
        HasPublicMember(domainEventType, "Id").Should().BeTrue();
        HasPublicMember(domainEventType, "SpecVersion").Should().BeTrue();
        HasPublicMember(domainEventType, "DataContentType").Should().BeTrue();
    }

    private static bool HasPublicMember(Type type, string name)
    {
        return type.GetProperty(name) is not null || type.GetField(name) is not null;
    }

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, ".taskmaster")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root from test execution directory.");
    }

    private static JsonElement LoadTask6FromMaster(string repoRoot)
    {
        var masterPath = Path.Combine(repoRoot, ".taskmaster", "tasks", "tasks.json");
        File.Exists(masterPath).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(masterPath));
        var tasks = doc.RootElement
            .GetProperty("master")
            .GetProperty("tasks")
            .EnumerateArray()
            .ToArray();

        var task6 = tasks.FirstOrDefault(x => TryGetInt(x, "id", out var id) && id == 6);
        task6.ValueKind.Should().NotBe(JsonValueKind.Undefined, "Task 6 must exist in tasks.json");
        return task6.Clone();
    }

    private static void ValidateViewAdrRefs(string repoRoot, string fileName)
    {
        var viewPath = Path.Combine(repoRoot, ".taskmaster", "tasks", fileName);
        File.Exists(viewPath).Should().BeTrue();

        using var doc = JsonDocument.Parse(File.ReadAllText(viewPath));
        var item = doc.RootElement
            .EnumerateArray()
            .FirstOrDefault(x => TryGetInt(x, "taskmaster_id", out var id) && id == 6);
        item.ValueKind.Should().NotBe(JsonValueKind.Undefined, $"Task 6 must exist in {fileName}");

        var adrRefs = item.GetProperty("adr_refs")
            .EnumerateArray()
            .Select(x => x.GetString())
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .ToArray();
        adrRefs.Should().Contain(RequiredAdrIds);
    }

    private static bool TryGetInt(JsonElement element, string propertyName, out int value)
    {
        value = default;
        if (!element.TryGetProperty(propertyName, out var prop))
        {
            return false;
        }

        return prop.ValueKind switch
        {
            JsonValueKind.Number => prop.TryGetInt32(out value),
            JsonValueKind.String => int.TryParse(prop.GetString(), out value),
            _ => false,
        };
    }

    private static string ResolveRepoPath(string repoRoot, string relativePath)
    {
        var normalized = relativePath.Replace('/', Path.DirectorySeparatorChar);
        return Path.GetFullPath(Path.Combine(repoRoot, normalized));
    }
}
