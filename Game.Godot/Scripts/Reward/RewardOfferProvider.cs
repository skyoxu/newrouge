using System;
using System.Collections.Generic;
using System.Text.Json;
using Game.Core.Services;
using Godot;

namespace Game.Godot.Scripts.Reward;

/// <summary>
/// Bridges Reward first-entry offer generation into the shared CardPool path.
/// </summary>
[GlobalClass]
public partial class RewardOfferProvider : Node
{
    private sealed record CardTextMetadata(string NameKey, string DescriptionKey, string Form);
    private static readonly string[] CardDefinitionCatalogPaths =
    {
        "res://Game.Core/Data/m1-card-definitions.json",
        "res://../Game.Core/Data/m1-card-definitions.json",
    };
    private static readonly JsonDocumentOptions CardDefinitionJsonOptions = new()
    {
        MaxDepth = 128,
    };

    private static readonly Lazy<IReadOnlyDictionary<string, CardTextMetadata>> CardTextCatalog =
        new(LoadCardTextCatalog);

    private readonly OfferPreviewService _offerPreviewService = new();

    public global::Godot.Collections.Array BuildFirstEntryOfferForContext(
        int actId,
        string encounterType,
        int deterministicSeed,
        int streamPosition = 0,
        int pickCount = 3,
        string contextId = "",
        string rewardPoolId = "")
    {
        var offers = new global::Godot.Collections.Array();
        if (pickCount <= 0)
        {
            return offers;
        }

        try
        {
            var selectedCardIds = ResolveOfferCardIds(
                actId,
                encounterType,
                deterministicSeed,
                streamPosition,
                pickCount,
                contextId,
                rewardPoolId);

            var index = 0;
            foreach (var cardId in selectedCardIds)
            {
                index += 1;
                var metadata = ResolveCardTextMetadata(cardId);
                offers.Add(new global::Godot.Collections.Dictionary
                {
                    { "id", cardId },
                    { "name_key", metadata.NameKey },
                    { "description_key", metadata.DescriptionKey },
                    { "name", metadata.NameKey },
                    { "description", metadata.DescriptionKey },
                    { "form", metadata.Form },
                    { "selectable", true },
                    { "source", "shared-card-pool" },
                    { "offer_index", index },
                });
            }
        }
        catch (Exception ex)
        {
            GD.PushWarning($"[RewardOfferProvider] failed to build first-entry offer: {ex.Message}");
        }

        return offers;
    }

    private IReadOnlyList<string> ResolveOfferCardIds(
        int actId,
        string encounterType,
        int deterministicSeed,
        long streamPosition,
        int pickCount,
        string contextId,
        string rewardPoolId)
    {
        if (string.Equals(rewardPoolId?.Trim(), "reward.act1.normal_1", StringComparison.Ordinal))
        {
            return new[]
            {
                "card.warrior.heavy_strike",
                "card.warrior.cleave",
                "card.warrior.defend",
            };
        }

        var preview = _offerPreviewService.PreviewSelection(
            act: actId,
            encounterType: encounterType,
            seed: deterministicSeed,
            streamPosition: streamPosition,
            pickCount: pickCount,
            poolId: rewardPoolId);
        return preview.SelectedCardIds;
    }

    private static CardTextMetadata ResolveCardTextMetadata(string cardId)
    {
        if (!string.IsNullOrWhiteSpace(cardId) && CardTextCatalog.Value.TryGetValue(cardId, out var metadata))
        {
            return metadata;
        }

        var normalized = string.IsNullOrWhiteSpace(cardId) ? "card.unknown" : cardId.Trim();
        return new CardTextMetadata(
            NameKey: normalized + ".name",
            DescriptionKey: normalized + ".description",
            Form: "Base");
    }

    private static IReadOnlyDictionary<string, CardTextMetadata> LoadCardTextCatalog()
    {
        var map = new Dictionary<string, CardTextMetadata>(StringComparer.Ordinal);
        var resolvedPath = ResolveCardDefinitionCatalogPath();
        if (string.IsNullOrWhiteSpace(resolvedPath))
        {
            GD.PushWarning("[RewardOfferProvider] card definition file not found in candidate paths.");
            return map;
        }

        try
        {
            using var file = FileAccess.Open(resolvedPath, FileAccess.ModeFlags.Read);
            if (file is null)
            {
                GD.PushWarning($"[RewardOfferProvider] card definition file could not be opened: {resolvedPath}");
                return map;
            }

            using var doc = JsonDocument.Parse(file.GetAsText(), CardDefinitionJsonOptions);
            if (!doc.RootElement.TryGetProperty("cards", out var cards) || cards.ValueKind != JsonValueKind.Array)
            {
                return map;
            }

            foreach (var card in cards.EnumerateArray())
            {
                if (!TryReadString(card, "id", out var id) ||
                    !TryReadString(card, "name_key", out var nameKey) ||
                    !TryReadString(card, "description_key", out var descriptionKey))
                {
                    continue;
                }

                var form = "Base";
                if (TryReadString(card, "default_form", out var defaultForm) && !string.IsNullOrWhiteSpace(defaultForm))
                {
                    form = defaultForm.Trim();
                }

                map[id] = new CardTextMetadata(
                    NameKey: nameKey,
                    DescriptionKey: descriptionKey,
                    Form: form);
            }
        }
        catch (Exception ex)
        {
            GD.PushWarning($"[RewardOfferProvider] failed to load card definition metadata: {ex.Message}");
        }

        return map;
    }

    private static string ResolveCardDefinitionCatalogPath()
    {
        foreach (var candidate in CardDefinitionCatalogPaths)
        {
            if (FileAccess.FileExists(candidate))
            {
                return candidate;
            }
        }

        return string.Empty;
    }

    private static bool TryReadString(JsonElement source, string key, out string value)
    {
        value = string.Empty;
        if (!source.TryGetProperty(key, out var property) || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var text = property.GetString();
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        value = text.Trim();
        return true;
    }
}
