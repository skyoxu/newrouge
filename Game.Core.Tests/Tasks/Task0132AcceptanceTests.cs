using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Domain;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0132AcceptanceTests
{
    private const string ThisTestRef = "Game.Core.Tests/Tasks/Task0132AcceptanceTests.cs";
    private const string RelicDefinitionsPath = "Game.Core/Data/m1-relic-definitions.json";
    private const string RewardPoolsPath = "Game.Core/Data/m1-reward-pools.json";
    private const string StartingRelicSourcePath = "Game.Core/Services/StartingRelicService.cs";

    // ACC:T132.1
    [Fact]
    [Trait("acceptance", "ACC:T132.1")]
    public void ShouldResolveRealConfiguredGameplayEffects_WhenEnumeratingObtainableLiveRelics()
    {
        var obtainableRelicIds = EnumerateObtainableLiveRelicIds().ToArray();
        var liveDefinitions = LoadLiveRelicDefinitions();

        obtainableRelicIds.Should().NotBeEmpty();

        var missingDefinitions = obtainableRelicIds
            .Where(relicId => !liveDefinitions.ContainsKey(relicId))
            .ToArray();

        missingDefinitions.Should().BeEmpty(
            "every relic obtainable from the live starting set or reward pools must have a governed live definition before Task 132 can close");

        var nonExecutableRelics = obtainableRelicIds
            .Where(relicId => liveDefinitions.ContainsKey(relicId) && !HasExecutableEffectMetadata(liveDefinitions[relicId]))
            .ToArray();

        nonExecutableRelics.Should().BeEmpty(
            "real live relic effects must declare timing, execution boundary, trigger path, target domain, and parameters rather than placeholder identity-only metadata");
    }

    // ACC:T132.2
    [Fact]
    [Trait("acceptance", "ACC:T132.2")]
    public void ShouldRouteImplementedEffectsThroughSharedBoundaries_WhenReadingCatalogMetadata()
    {
        var catalogEntries = LoadLiveRelicDefinitions()
            .Values
            .Where(definition => HasNonPlaceholderString(definition, "effect_key"))
            .Select(BuildCatalogEntry)
            .ToArray();

        catalogEntries.Should().NotBeEmpty("the live relic catalog should expose implemented effect entries for obtainable relics");
        catalogEntries.Should().OnlyContain(entry =>
            string.Equals(entry.ExecutionBoundary, "t99.shared.combat", StringComparison.Ordinal)
            || string.Equals(entry.ExecutionBoundary, "t110.shared.run", StringComparison.Ordinal),
            "implemented relic effects must resolve only through the shared combat or shared run trigger boundaries");

        catalogEntries
            .Where(entry => string.Equals(entry.ExecutionBoundary, "t99.shared.combat", StringComparison.Ordinal))
            .Should()
            .OnlyContain(entry => string.Equals(entry.TriggerPath, "core.combat.relic.triggered", StringComparison.Ordinal),
                "combat-time relic effects must use the existing shared T99 trigger path");

        catalogEntries
            .Where(entry => string.Equals(entry.ExecutionBoundary, "t110.shared.run", StringComparison.Ordinal))
            .Should()
            .OnlyContain(entry => !entry.TriggerPath.Contains("Scene", StringComparison.Ordinal)
                && !entry.TriggerPath.Contains("Main", StringComparison.Ordinal),
                "implemented non-combat relic effects must not be owned by scene-local trigger authority");
    }

    // ACC:T132.3
    [Fact]
    [Trait("acceptance", "ACC:T132.3")]
    public void ShouldRefuseSilentExposure_WhenObtainableRelicHasNoGovernedEffect()
    {
        var startingRelicIds = StartingRelicService.LiveDefinitions
            .Select(definition => definition.RelicId)
            .ToHashSet(StringComparer.Ordinal);
        var rewardPoolExposures = LoadRewardPoolRelicExposures();
        var liveDefinitions = LoadLiveRelicDefinitions();

        var unavailableRelicIds = EnumerateObtainableLiveRelicIds()
            .Where(relicId => !liveDefinitions.TryGetValue(relicId, out var definition) || !HasExecutableEffectMetadata(definition))
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        var silentlyExposedRelicIds = unavailableRelicIds
            .Where(relicId => startingRelicIds.Contains(relicId)
                || rewardPoolExposures.Any(exposure => string.Equals(exposure.RelicId, relicId, StringComparison.Ordinal) && !exposure.IsUnavailableFallback))
            .ToArray();

        silentlyExposedRelicIds.Should().BeEmpty(
            "every non-executable relic must either be removed from live obtainable sources or surfaced through a deterministic unavailable-for-selection fallback");
    }

    // ACC:T132.4
    [Fact]
    [Trait("acceptance", "ACC:T132.4")]
    public void ShouldLoadTimingBoundaryAndParametersFromConfiguration_WhenValidatingCatalogDefinitions()
    {
        var definitions = LoadLiveRelicDefinitions().Values.ToArray();
        var definitionFileText = ReadRepoText(RelicDefinitionsPath);

        definitions.Should().NotBeEmpty();
        definitions.Should().OnlyContain(definition =>
            HasNonPlaceholderString(definition, "timing")
            && HasNonPlaceholderString(definition, "target_domain")
            && HasParametersObject(definition),
            "the relic effect catalog must be configuration-driven with governed timing, target domain, and numeric parameter payloads");

        definitionFileText.Should().NotContain("CombatScene", "catalog definitions must not depend on scene glue");
        definitionFileText.Should().NotContain("MainMenu", "catalog definitions must not depend on scene glue");
        definitionFileText.Should().NotContain(".tscn", "catalog definitions must remain scene-agnostic data");
    }

    // ACC:T132.5
    [Fact]
    [Trait("acceptance", "ACC:T132.5")]
    public void ShouldMatchOutcomeAttributionText_WhenConfiguredEffectDefinitionsAreRendered()
    {
        var implementedDefinitions = LoadLiveRelicDefinitions()
            .Values
            .Where(definition => HasNonPlaceholderString(definition, "effect_key"))
            .ToArray();

        implementedDefinitions.Should().NotBeEmpty();
        implementedDefinitions.Should().OnlyContain(definition =>
            HasNonPlaceholderString(definition, "description_key")
            && HasNonPlaceholderString(definition, "outcome_text_key")
            && HasNonPlaceholderString(definition, "attribution_key"),
            "player-visible relic text must be bound to the effect that actually executes instead of stale placeholder descriptions");

        implementedDefinitions.Should().OnlyContain(definition =>
            !string.Equals(ReadString(definition, "description_key"), ReadString(definition, "outcome_text_key"), StringComparison.Ordinal),
            "outcome evidence must be distinct from generic description text so execution attribution can be validated");
    }

    // ACC:T132.6
    [Fact]
    [Trait("acceptance", "ACC:T132.6")]
    public void ShouldPreserveUniquenessOwnershipAndDeterministicReplay_WhenGrantingConfiguredRelicRewards()
    {
        var validRelicIds = StartingRelicService.LiveDefinitions
            .Select(definition => definition.RelicId)
            .ToHashSet(StringComparer.Ordinal);
        var firstRelicId = StartingRelicService.LiveDefinitions[0].RelicId;
        var secondRelicId = StartingRelicService.LiveDefinitions[1].RelicId;
        var inventory = new Inventory();
        var inventoryService = new InventoryService(inventory, maxSlots: 10);
        var service = new RunRelicStateService(
            inventoryService,
            relicId => $"name::{relicId}",
            validRelicIdSet: validRelicIds);

        var firstGrant = service.TryGrantAndEquip(firstRelicId);
        var duplicateGrant = service.TryGrantAndEquip(firstRelicId);
        var secondGrant = service.TryGrantAndEquip(secondRelicId);
        var firstSnapshot = service.CreateSnapshot();
        var secondSnapshot = service.CreateSnapshot();
        var rewardPoolIdsFirstRead = LoadRewardPoolIds();
        var rewardPoolIdsSecondRead = LoadRewardPoolIds();

        firstGrant.Should().BeTrue();
        duplicateGrant.Should().BeFalse("duplicate ownership must still be rejected after live relic reward promotion");
        secondGrant.Should().BeTrue();
        firstSnapshot.Should().BeEquivalentTo(secondSnapshot, "snapshot replay must stay deterministic for the same shared run state");
        firstSnapshot.AcquiredRelicIds.Should().OnlyHaveUniqueItems();
        rewardPoolIdsSecondRead.Should().Equal(rewardPoolIdsFirstRead, "reward-path discovery must stay deterministic across identical reads");
    }

    // ACC:T132.5
    [Fact]
    [Trait("acceptance", "ACC:T132.5")]
    public void ShouldApplyCombatStartEnergyBonusFromLiveCatalog_WhenAshenHourglassIsEquipped()
    {
        var catalog = RelicEffectCatalogService.Parse(ReadRepoText(RelicDefinitionsPath));

        var resolution = RelicEffectRuntimeService.ResolveCombatStartEffects(
            baseEnergy: 3,
            activeRelicIds: new[] { "relic.ashen_hourglass" },
            catalog);

        resolution.AdjustedEnergy.Should().Be(4, "the live combat relic catalog should drive a real combat-start energy bonus instead of placeholder-only identity text");
        resolution.Effects.Should().ContainSingle(effect =>
            effect.RelicId == "relic.ashen_hourglass"
            && effect.ExecutionBoundary == "t99.shared.combat"
            && effect.TriggerPath == "core.combat.relic.triggered");
    }

    // ACC:T132.5
    [Fact]
    [Trait("acceptance", "ACC:T132.5")]
    public void ShouldApplyShopDiscountFromLiveCatalog_WhenTwilightCoinIsEquipped()
    {
        var catalog = RelicEffectCatalogService.Parse(ReadRepoText(RelicDefinitionsPath));

        var resolution = RelicEffectRuntimeService.ResolveShopOpenEffects(
            basePrice: 120,
            activeRelicIds: new[] { "relic.twilight_coin" },
            catalog);

        resolution.AdjustedPrice.Should().Be(108, "the live run-boundary relic catalog should drive observable shop discounts instead of leaving obtainable relics as placeholder text");
        resolution.Effects.Should().ContainSingle(effect =>
            effect.RelicId == "relic.twilight_coin"
            && effect.ExecutionBoundary == "t110.shared.run"
            && effect.TriggerPath == "core.relic.equipped");
    }

    // ACC:T132.5
    [Fact]
    [Trait("acceptance", "ACC:T132.5")]
    public void ShouldLeaveRuntimeStateUnchanged_WhenRelicIsUnknownOrNotLiveImplemented()
    {
        var catalog = RelicEffectCatalogService.Parse(ReadRepoText(RelicDefinitionsPath));

        var combatResolution = RelicEffectRuntimeService.ResolveCombatStartEffects(
            baseEnergy: 3,
            activeRelicIds: new[] { "relic.unknown", "relic.obsidian_mirror" },
            catalog);
        var shopResolution = RelicEffectRuntimeService.ResolveShopOpenEffects(
            basePrice: 120,
            activeRelicIds: new[] { "relic.unknown", "relic.raven_feather" },
            catalog);

        combatResolution.AdjustedEnergy.Should().Be(3, "unknown or contract-only relic ids must not silently mutate combat energy");
        combatResolution.Effects.Should().BeEmpty();
        shopResolution.AdjustedPrice.Should().Be(120, "unknown or contract-only relic ids must not silently mutate live shop prices");
        shopResolution.Effects.Should().BeEmpty();
    }

    // ACC:T132.7
    [Fact]
    [Trait("acceptance", "ACC:T132.7")]
    public void ShouldCoverCatalogEligibilityBoundaryExecutionAndVisibleEvidence_WhenAuditingThisAcceptanceFile()
    {
        var source = ReadRepoText(ThisTestRef);

        source.Should().Contain("ACC:T132.1");
        source.Should().Contain("ACC:T132.2");
        source.Should().Contain("ACC:T132.3");
        source.Should().Contain("ACC:T132.4");
        source.Should().Contain("ACC:T132.5");
        source.Should().Contain("ACC:T132.6");
        source.Should().Contain("ACC:T132.7");
        source.Should().Contain(nameof(ShouldResolveRealConfiguredGameplayEffects_WhenEnumeratingObtainableLiveRelics));
        source.Should().Contain(nameof(ShouldRefuseSilentExposure_WhenObtainableRelicHasNoGovernedEffect));
        source.Should().Contain(nameof(ShouldRouteImplementedEffectsThroughSharedBoundaries_WhenReadingCatalogMetadata));
        source.Should().Contain(nameof(ShouldMatchOutcomeAttributionText_WhenConfiguredEffectDefinitionsAreRendered));
        source.Should().Contain(nameof(ShouldApplyCombatStartEnergyBonusFromLiveCatalog_WhenAshenHourglassIsEquipped));
        source.Should().Contain(nameof(ShouldApplyShopDiscountFromLiveCatalog_WhenTwilightCoinIsEquipped));
    }

    private static IReadOnlyCollection<string> EnumerateObtainableLiveRelicIds()
    {
        var liveRelicIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var definition in StartingRelicService.LiveDefinitions)
        {
            liveRelicIds.Add(definition.RelicId);
        }

        foreach (var rewardPoolRelic in LoadRewardPoolRelicExposures())
        {
            if (rewardPoolRelic.IsUnavailableFallback)
            {
                continue;
            }

            liveRelicIds.Add(rewardPoolRelic.RelicId);
        }

        return liveRelicIds;
    }

    private static Dictionary<string, JsonElement> LoadLiveRelicDefinitions()
    {
        using var document = JsonDocument.Parse(ReadRepoText(RelicDefinitionsPath));
        var definitions = new Dictionary<string, JsonElement>(StringComparer.Ordinal);

        foreach (var relicNode in document.RootElement.GetProperty("relics").EnumerateArray())
        {
            var relicId = ReadString(relicNode, "id");
            if (string.IsNullOrWhiteSpace(relicId))
            {
                continue;
            }

            definitions[relicId] = relicNode.Clone();
        }

        return definitions;
    }

    private static IReadOnlyList<RewardPoolRelicExposure> LoadRewardPoolRelicExposures()
    {
        using var document = JsonDocument.Parse(ReadRepoText(RewardPoolsPath));
        var exposures = new List<RewardPoolRelicExposure>();

        foreach (var poolNode in document.RootElement.GetProperty("reward_pools").EnumerateArray())
        {
            var poolId = ReadString(poolNode, "id");
            if (!poolNode.TryGetProperty("entries", out var entriesNode)
                || !entriesNode.TryGetProperty("relic", out var relicNode)
                || relicNode.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            var relicId = ReadString(relicNode, "relic_id");
            if (string.IsNullOrWhiteSpace(relicId))
            {
                continue;
            }

            var isUnavailableFallback = string.Equals(ReadString(relicNode, "selection_state"), "unavailable", StringComparison.Ordinal)
                || string.Equals(ReadString(relicNode, "availability"), "unavailable", StringComparison.Ordinal)
                || HasNonPlaceholderString(relicNode, "fallback_reason_key");

            exposures.Add(new RewardPoolRelicExposure(poolId, relicId, isUnavailableFallback));
        }

        return exposures;
    }

    private static string[] LoadRewardPoolIds()
    {
        using var document = JsonDocument.Parse(ReadRepoText(RewardPoolsPath));
        return document.RootElement
            .GetProperty("reward_pools")
            .EnumerateArray()
            .Select(poolNode => ReadString(poolNode, "id"))
            .Where(poolId => !string.IsNullOrWhiteSpace(poolId))
            .ToArray();
    }

    private static RelicEffectCatalogEntry BuildCatalogEntry(JsonElement definition)
    {
        var parameters = definition.TryGetProperty("parameters", out var parameterNode)
            && parameterNode.ValueKind == JsonValueKind.Object;

        return new RelicEffectCatalogEntry(
            ReadString(definition, "id"),
            ReadString(definition, "effect_key"),
            ReadString(definition, "execution_boundary"),
            ReadString(definition, "trigger_path"),
            ReadString(definition, "timing"),
            ReadString(definition, "target_domain"),
            parameters);
    }

    private static bool HasExecutableEffectMetadata(JsonElement definition)
    {
        var entry = BuildCatalogEntry(definition);
        return !string.IsNullOrWhiteSpace(entry.EffectKey)
            && !string.IsNullOrWhiteSpace(entry.ExecutionBoundary)
            && !string.IsNullOrWhiteSpace(entry.TriggerPath)
            && !string.IsNullOrWhiteSpace(entry.Timing)
            && !string.IsNullOrWhiteSpace(entry.TargetDomain)
            && entry.HasParametersObject;
    }

    private static bool HasParametersObject(JsonElement definition)
    {
        return definition.TryGetProperty("parameters", out var parameters)
            && parameters.ValueKind == JsonValueKind.Object;
    }

    private static bool HasNonPlaceholderString(JsonElement node, string propertyName)
    {
        var value = ReadString(node, propertyName);
        return !string.IsNullOrWhiteSpace(value)
            && !value.Contains("placeholder", StringComparison.OrdinalIgnoreCase)
            && !value.Contains("todo", StringComparison.OrdinalIgnoreCase)
            && !value.Contains("tbd", StringComparison.OrdinalIgnoreCase);
    }

    private static string ReadString(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var propertyNode) || propertyNode.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return propertyNode.GetString() ?? string.Empty;
    }

    private static string ReadRepoText(string repoRelativePath)
    {
        var absolutePath = Path.Combine(FindRepositoryRoot(), repoRelativePath.Replace('/', Path.DirectorySeparatorChar));
        File.Exists(absolutePath).Should().BeTrue($"expected repository file to exist: {repoRelativePath}");
        return File.ReadAllText(absolutePath);
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current.FullName, "NewRouge.sln")))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Unable to locate repository root containing NewRouge.sln.");
    }

    private sealed record RewardPoolRelicExposure(
        string PoolId,
        string RelicId,
        bool IsUnavailableFallback);

    private sealed record RelicEffectCatalogEntry(
        string RelicId,
        string EffectKey,
        string ExecutionBoundary,
        string TriggerPath,
        string Timing,
        string TargetDomain,
        bool HasParametersObject);
}
