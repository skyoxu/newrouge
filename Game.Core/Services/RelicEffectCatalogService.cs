using System;
using System.Text.Json;
using Game.Core.Contracts;

namespace Game.Core.Services;

public sealed record RelicEffectDefinition(
    string RelicId,
    string NameKey,
    string DescriptionKey,
    string EffectKey,
    string ExecutionBoundary,
    string TriggerPath,
    string Timing,
    string TargetDomain,
    string OutcomeTextKey,
    string AttributionKey,
    IReadOnlyDictionary<string, int> NumericParameters)
{
    public int GetNumericParameter(string key, int fallback = 0)
    {
        return NumericParameters.TryGetValue(key, out var value) ? value : fallback;
    }
}

public sealed record CombatRelicResolution(
    int AdjustedEnergy,
    IReadOnlyList<ResolvedRelicEffect> Effects);

public sealed record ShopRelicResolution(
    int AdjustedPrice,
    IReadOnlyList<ResolvedRelicEffect> Effects);

public sealed record ResolvedRelicEffect(
    string RelicId,
    string EffectKey,
    string ExecutionBoundary,
    string TriggerPath,
    string Timing,
    IReadOnlyDictionary<string, int> NumericParameters);

public static class RelicEffectCatalogService
{
    public static IReadOnlyDictionary<string, RelicEffectDefinition> Parse(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return new Dictionary<string, RelicEffectDefinition>(StringComparer.Ordinal);
        }

        using var document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("relics", out var relicsNode)
            || relicsNode.ValueKind != JsonValueKind.Array)
        {
            return new Dictionary<string, RelicEffectDefinition>(StringComparer.Ordinal);
        }

        var definitions = new Dictionary<string, RelicEffectDefinition>(StringComparer.Ordinal);
        foreach (var relicNode in relicsNode.EnumerateArray())
        {
            var relicId = ReadString(relicNode, "id");
            if (string.IsNullOrWhiteSpace(relicId))
            {
                continue;
            }

            definitions[relicId] = new RelicEffectDefinition(
                RelicId: relicId,
                NameKey: ReadString(relicNode, "name_key"),
                DescriptionKey: ReadString(relicNode, "description_key"),
                EffectKey: ReadString(relicNode, "effect_key"),
                ExecutionBoundary: ReadString(relicNode, "execution_boundary"),
                TriggerPath: ReadString(relicNode, "trigger_path"),
                Timing: ReadString(relicNode, "timing"),
                TargetDomain: ReadString(relicNode, "target_domain"),
                OutcomeTextKey: ReadString(relicNode, "outcome_text_key"),
                AttributionKey: ReadString(relicNode, "attribution_key"),
                NumericParameters: ReadNumericParameters(relicNode));
        }

        return definitions;
    }

    private static IReadOnlyDictionary<string, int> ReadNumericParameters(JsonElement relicNode)
    {
        var parameters = new Dictionary<string, int>(StringComparer.Ordinal);
        if (!relicNode.TryGetProperty("parameters", out var parameterNode)
            || parameterNode.ValueKind != JsonValueKind.Object)
        {
            return parameters;
        }

        foreach (var property in parameterNode.EnumerateObject())
        {
            if (property.Value.ValueKind == JsonValueKind.Number && property.Value.TryGetInt32(out var intValue))
            {
                parameters[property.Name] = intValue;
            }
        }

        return parameters;
    }

    private static string ReadString(JsonElement node, string propertyName)
    {
        if (!node.TryGetProperty(propertyName, out var propertyNode)
            || propertyNode.ValueKind != JsonValueKind.String)
        {
            return string.Empty;
        }

        return propertyNode.GetString() ?? string.Empty;
    }
}

public static class RelicEffectRuntimeService
{
    public static CombatRelicResolution ResolveCombatStartEffects(
        int baseEnergy,
        IEnumerable<string> activeRelicIds,
        IReadOnlyDictionary<string, RelicEffectDefinition> catalog)
    {
        var adjustedEnergy = Math.Max(0, baseEnergy);
        var effects = new List<ResolvedRelicEffect>();
        foreach (var definition in ResolveActiveDefinitions(activeRelicIds, catalog))
        {
            if (!string.Equals(definition.ExecutionBoundary, "t99.shared.combat", StringComparison.Ordinal)
                || !string.Equals(definition.TriggerPath, EventTypes.CombatRelicTriggered, StringComparison.Ordinal)
                || !string.Equals(definition.Timing, "on_combat_start", StringComparison.Ordinal)
                || !string.Equals(definition.EffectKey, "effect.turn_start_plus_energy", StringComparison.Ordinal))
            {
                continue;
            }

            adjustedEnergy += Math.Max(0, definition.GetNumericParameter("energy_bonus"));
            effects.Add(ToResolvedEffect(definition));
        }

        return new CombatRelicResolution(adjustedEnergy, effects);
    }

    public static ShopRelicResolution ResolveShopOpenEffects(
        int basePrice,
        IEnumerable<string> activeRelicIds,
        IReadOnlyDictionary<string, RelicEffectDefinition> catalog)
    {
        var normalizedPrice = Math.Max(0, basePrice);
        var totalDiscountPercent = 0;
        var effects = new List<ResolvedRelicEffect>();

        foreach (var definition in ResolveActiveDefinitions(activeRelicIds, catalog))
        {
            if (!string.Equals(definition.ExecutionBoundary, "t110.shared.run", StringComparison.Ordinal)
                || !string.Equals(definition.TriggerPath, EventTypes.RelicEquipped, StringComparison.Ordinal)
                || !string.Equals(definition.Timing, "on_shop_offer_open", StringComparison.Ordinal)
                || !string.Equals(definition.EffectKey, "effect.shop_discount_small", StringComparison.Ordinal))
            {
                continue;
            }

            totalDiscountPercent += Math.Max(0, definition.GetNumericParameter("discount_percent"));
            effects.Add(ToResolvedEffect(definition));
        }

        if (totalDiscountPercent <= 0)
        {
            return new ShopRelicResolution(normalizedPrice, effects);
        }

        totalDiscountPercent = Math.Min(100, totalDiscountPercent);
        return new ShopRelicResolution(
            Math.Max(0, normalizedPrice * (100 - totalDiscountPercent) / 100),
            effects);
    }

    public static int ApplyCombatStartEnergyBonuses(
        int baseEnergy,
        IEnumerable<string> activeRelicIds,
        IReadOnlyDictionary<string, RelicEffectDefinition> catalog)
    {
        return ResolveCombatStartEffects(baseEnergy, activeRelicIds, catalog).AdjustedEnergy;
    }

    public static int ApplyShopPriceDiscounts(
        int basePrice,
        IEnumerable<string> activeRelicIds,
        IReadOnlyDictionary<string, RelicEffectDefinition> catalog)
    {
        return ResolveShopOpenEffects(basePrice, activeRelicIds, catalog).AdjustedPrice;
    }

    private static IEnumerable<RelicEffectDefinition> ResolveActiveDefinitions(
        IEnumerable<string> activeRelicIds,
        IReadOnlyDictionary<string, RelicEffectDefinition> catalog)
    {
        foreach (var relicId in activeRelicIds)
        {
            if (string.IsNullOrWhiteSpace(relicId))
            {
                continue;
            }

            if (catalog.TryGetValue(relicId.Trim(), out var definition))
            {
                yield return definition;
            }
        }
    }

    private static ResolvedRelicEffect ToResolvedEffect(RelicEffectDefinition definition)
    {
        return new ResolvedRelicEffect(
            definition.RelicId,
            definition.EffectKey,
            definition.ExecutionBoundary,
            definition.TriggerPath,
            definition.Timing,
            definition.NumericParameters);
    }
}
