using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

public sealed class Task0039AcceptanceTests
{
    private const int TaskmasterId = 39;
    private const string ThisCSharpTestRef = "Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs";
    private const string ThisGdTestRef = "Tests.Godot/tests/Tasks/test_task0039_acceptance.gd";
    private static readonly string[] RequiredEventAndUiKeys =
    {
        "event.abyss_toll.title",
        "event.abyss_toll.description",
        "event.option.lose_hp",
        "event.option.take_curse",
        "ui.menu.new_run",
        "ui.menu.continue",
        "ui.menu.quit",
        "ui.menu.confirm",
        "ui.menu.cancel",
        "ui.character.warrior.summary.rage_buff",
        "ui.character.warrior.summary.power_window",
        "ui.character.warrior.summary.cost_burst",
    };

    // ACC:T39.1
    [Fact]
    public void ShouldContainCardRelicEventAndUiTranslationKeys_WhenValidatingTask39TranslationCoverage()
    {
        var repositoryRoot = FindRepositoryRoot();
        var enMap = LoadTranslationMap(Path.Combine(repositoryRoot, "Game.Godot", "Translations", "en.csv"));
        var zhMap = LoadTranslationMap(Path.Combine(repositoryRoot, "Game.Godot", "Translations", "zh-CN.csv"));

        var requiredKeys = BuildRequiredTranslationKeys();
        var missing = CollectMissing(requiredKeys, enMap, zhMap);

        missing.Should().BeEmpty("Task 39 requires en/zh-CN coverage for cards/relics/events/ui visible keys");
    }

    // ACC:T39.2
    [Fact]
    public void ShouldCoverAllWarriorCardAndRelicKeys_WhenCrossCheckingDefinitionsAgainstTranslations()
    {
        var repositoryRoot = FindRepositoryRoot();
        var enMap = LoadTranslationMap(Path.Combine(repositoryRoot, "Game.Godot", "Translations", "en.csv"));
        var zhMap = LoadTranslationMap(Path.Combine(repositoryRoot, "Game.Godot", "Translations", "zh-CN.csv"));

        var cardNameKeys = WarriorStartingDeckService.Definitions
            .Select(card => $"{card.CardId}.name")
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        var relicKeys = StartingRelicService.Definitions
            .Select(relic => relic.TranslationKey)
            .Distinct(StringComparer.Ordinal)
            .ToArray();

        cardNameKeys.Should().NotBeEmpty();
        relicKeys.Should().NotBeEmpty();

        var missingCards = CollectMissing(cardNameKeys, enMap, zhMap);
        var missingRelics = CollectMissing(relicKeys, enMap, zhMap);
        (missingCards.Concat(missingRelics)).Should().BeEmpty("definition-derived keys must be present in both locales");
    }

    // ACC:T39.1
    [Fact]
    public void ShouldMarkInvalidTranslationValuesAsMissing_WhenCollectingCoverage()
    {
        var required = new[] { "event.abyss_toll.title" };
        var enMap = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["event.abyss_toll.title"] = "event.abyss_toll.title",
        };
        var zhMap = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["event.abyss_toll.title"] = "(ZH) placeholder",
        };

        var missing = CollectMissing(required, enMap, zhMap);

        missing.Should().Contain("en::event.abyss_toll.title::invalid_value");
        missing.Should().Contain("zh-CN::event.abyss_toll.title::invalid_value");
    }

    // governance: adr-and-test-refs
    [Fact]
    public void ShouldIncludeAdr0010AndTaskScopedTestRefs_WhenReadingTask39Metadata()
    {
        using var metadata = ReadGameplayTaskMetadata();
        var root = metadata.RootElement;

        ReadStringArray(root, "adr_refs").Should().Contain("ADR-0010");

        var testRefs = ReadStringArray(root, "test_refs");
        testRefs.Should().Contain(ThisCSharpTestRef);
        testRefs.Should().Contain(ThisGdTestRef);
        testRefs.Should().OnlyHaveUniqueItems();
    }

    // supplemental: contract-refs
    [Fact]
    public void ShouldDeclareContractRefs_WhenReadingTask39Metadata()
    {
        using var metadata = ReadGameplayTaskMetadata();
        var contractRefs = ReadStringArray(metadata.RootElement, "contractRefs");

        contractRefs.Should().NotBeEmpty();
        contractRefs.Should().Contain("core.event.entered");
        contractRefs.Should().Contain("core.relic.granted");
    }

    private static string[] BuildRequiredTranslationKeys()
    {
        var required = new HashSet<string>(RequiredEventAndUiKeys, StringComparer.Ordinal);
        foreach (var card in WarriorStartingDeckService.Definitions)
        {
            required.Add($"{card.CardId}.name");
        }

        foreach (var relic in StartingRelicService.Definitions)
        {
            required.Add(relic.TranslationKey);
        }

        return required.OrderBy(item => item, StringComparer.Ordinal).ToArray();
    }

    private static List<string> CollectMissing(IEnumerable<string> requiredKeys, Dictionary<string, string> enMap, Dictionary<string, string> zhMap)
    {
        var missing = new List<string>();
        foreach (var key in requiredKeys)
        {
            if (!enMap.TryGetValue(key, out var enValue))
            {
                missing.Add($"en::{key}");
            }
            else if (!IsTranslationValueValid(key, enValue, "en"))
            {
                missing.Add($"en::{key}::invalid_value");
            }

            if (!zhMap.TryGetValue(key, out var zhValue))
            {
                missing.Add($"zh-CN::{key}");
            }
            else if (!IsTranslationValueValid(key, zhValue, "zh-CN"))
            {
                missing.Add($"zh-CN::{key}::invalid_value");
            }
        }

        return missing;
    }

    private static bool IsTranslationValueValid(string key, string? value, string locale)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        var trimmed = value.Trim();
        if (string.Equals(trimmed, key, StringComparison.Ordinal))
        {
            return false;
        }

        if (trimmed.All(ch => ch is '?' or '？'))
        {
            return false;
        }

        if (trimmed.Contains('�'))
        {
            return false;
        }

        if (string.Equals(locale, "zh-CN", StringComparison.OrdinalIgnoreCase)
            && trimmed.Contains("(ZH)", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return true;
    }

    private static JsonDocument ReadGameplayTaskMetadata()
    {
        var gameplayPath = Path.Combine(
            FindRepositoryRoot(),
            ".taskmaster",
            "tasks",
            "tasks_gameplay.json");
        var json = File.ReadAllText(gameplayPath);
        using var document = JsonDocument.Parse(json);
        var taskNode = document.RootElement
            .EnumerateArray()
            .FirstOrDefault(item =>
                item.TryGetProperty("taskmaster_id", out var idNode) &&
                idNode.ValueKind == JsonValueKind.Number &&
                idNode.GetInt32() == TaskmasterId);

        taskNode.ValueKind.Should().NotBe(JsonValueKind.Undefined, "Task 39 metadata must exist in tasks_gameplay.json");
        return JsonDocument.Parse(taskNode.GetRawText());
    }

    private static IReadOnlyList<string> ReadStringArray(JsonElement node, string fieldName)
    {
        if (!node.TryGetProperty(fieldName, out var field) || field.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        var values = new List<string>();
        foreach (var entry in field.EnumerateArray())
        {
            if (entry.ValueKind == JsonValueKind.String)
            {
                var value = entry.GetString();
                if (!string.IsNullOrWhiteSpace(value))
                {
                    values.Add(value);
                }
            }
        }

        return values;
    }

    private static Dictionary<string, string> LoadTranslationMap(string csvPath)
    {
        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        if (!File.Exists(csvPath))
        {
            return map;
        }

        var lines = File.ReadAllLines(csvPath);
        foreach (var line in lines.Skip(1))
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                continue;
            }

            var separator = line.IndexOf(',');
            if (separator <= 0 || separator >= line.Length - 1)
            {
                continue;
            }

            var key = line[..separator].Trim();
            var value = line[(separator + 1)..].Trim();
            if (!string.IsNullOrWhiteSpace(key))
            {
                map[key] = value;
            }
        }

        return map;
    }

    private static string FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            var marker = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from test base directory.");
    }
}
