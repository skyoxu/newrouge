using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Godot;
using Game.Core.Contracts;
using Game.Godot.Adapters;

namespace Game.Godot.Scripts.UI;

public partial class EventScene : Control
{
    private sealed class PersistedEventState
    {
        public string SelectedOptionId { get; init; } = string.Empty;
        public int CurrentHp { get; init; } = 20;
        public List<string> DeckCardIds { get; init; } = new();
    }

    private sealed class EventOption
    {
        public EventOption(string id, string textKey, int hpLoss, int curseAdd)
        {
            Id = id;
            TextKey = textKey;
            HpLoss = hpLoss;
            CurseAdd = curseAdd;
        }

        public string Id { get; }
        public string TextKey { get; }
        public int HpLoss { get; }
        public int CurseAdd { get; }
    }

    private const string EventId = "event.abyss_toll";
    private const string NodeId = "event.node.default";
    private const string TitleKey = "event.abyss_toll.title";
    private const string DescriptionKey = "event.abyss_toll.description";
    private const string PreviewHpLossKey = "event.preview.hp_loss";
    private const string PreviewCurseKey = "event.preview.take_curse";
    private const string BlockedAlreadyCommittedKey = "event.feedback.blocked.already_committed";
    private const string BlockedInvalidOptionKey = "event.feedback.blocked.invalid_option";
    private const string BlockedPersistFailureKey = "event.feedback.blocked.persist_failed";
    private const string ChosenOptionLabelKey = "event.feedback.chosen_option";
    private const string ResultSummaryLoseHpKey = "event.feedback.summary.lose_hp";
    private const string ResultSummaryTakeCurseKey = "event.feedback.summary.take_curse";
    private const string ResultSummaryDefaultKey = "event.feedback.summary.default";
    private const string NumericChangesHpLossKey = "event.feedback.numeric.hp_loss";
    private const string NumericChangesTakeCurseKey = "event.feedback.numeric.take_curse";
    private const string NumericChangesDefaultKey = "event.feedback.numeric.default";
    private const string CurseCardId = "card.curse.basic";
    private const string PersistedStateFileName = "task22-event-state.json";

    private Label _titleLabel = default!;
    private Label _descriptionLabel = default!;
    private Button _loseHpButton = default!;
    private Button _takeCurseButton = default!;
    private Label _loseHpPreviewLabel = default!;
    private Label _takeCursePreviewLabel = default!;
    private Label _chosenOptionLabel = default!;
    private Label _resultSummaryLabel = default!;
    private Label _numericChangesLabel = default!;
    private Label _blockedFeedbackLabel = default!;
    private EventBusAdapter? _eventBus;

    private readonly List<EventOption> _lockedOptions = new();
    private readonly List<string> _deckCards = new();
    private string _selectedOptionId = string.Empty;
    private int _currentHp = 20;
    private bool _forcePersistFailureForTest;
    private string _lastPersistError = string.Empty;

    private static string _persistedSelectedOptionId = string.Empty;
    private static int _persistedHp = 20;
    private static readonly List<string> _persistedDeckCards = new();
    private static bool _persistedStateInitialized;

    public override void _Ready()
    {
        _titleLabel = GetNode<Label>("VBox/LblTitle");
        _descriptionLabel = GetNode<Label>("VBox/LblDescription");
        _loseHpButton = GetNode<Button>("VBox/Options/BtnLoseHp");
        _takeCurseButton = GetNode<Button>("VBox/Options/BtnTakeCurse");
        _loseHpPreviewLabel = GetNode<Label>("VBox/Options/LblLoseHpPreview");
        _takeCursePreviewLabel = GetNode<Label>("VBox/Options/LblTakeCursePreview");
        _chosenOptionLabel = GetNode<Label>("VBox/Feedback/LblChosenOption");
        _resultSummaryLabel = GetNode<Label>("VBox/Feedback/LblResultSummary");
        _numericChangesLabel = GetNode<Label>("VBox/Feedback/LblNumericChanges");
        _blockedFeedbackLabel = GetNode<Label>("VBox/Feedback/LblBlockedFeedback");

        _loseHpButton.Pressed += () => ChooseOptionForTest("lose_hp");
        _takeCurseButton.Pressed += () => ChooseOptionForTest("take_curse");

        EnterEventForTest();
    }

    public void EnterEventForTest()
    {
        EnsureLockedOptions();
        LoadPersistedState();
        RefreshLocalizationForTest();
        PublishEventEntered();
    }

    public void ResetStateForTest(int hp, int curseCards)
    {
        _currentHp = Math.Max(0, hp);
        _deckCards.Clear();
        for (var index = 0; index < Math.Max(0, curseCards); index++)
        {
            _deckCards.Add(CurseCardId);
        }
        _selectedOptionId = string.Empty;
        _lockedOptions.Clear();
        PersistRuntimeState();
        EnterEventForTest();
    }

    public bool ChooseOptionForTest(string optionId)
    {
        EnsureLockedOptions();
        if (!string.IsNullOrWhiteSpace(_selectedOptionId))
        {
            SetBlockedFeedbackByKey(BlockedAlreadyCommittedKey);
            return false;
        }

        var option = _lockedOptions.FirstOrDefault(item => item.Id == optionId);
        if (option is null)
        {
            SetBlockedFeedbackByKey(BlockedInvalidOptionKey);
            return false;
        }

        var nextHp = _currentHp;
        var nextDeckCards = new List<string>(_deckCards);

        if (option.HpLoss > 0)
        {
            nextHp = Math.Max(0, nextHp - option.HpLoss);
        }

        if (option.CurseAdd > 0)
        {
            for (var index = 0; index < option.CurseAdd; index++)
            {
                nextDeckCards.Add(CurseCardId);
            }
        }

        if (!PersistRuntimeState(nextHp, option.Id, nextDeckCards))
        {
            _lastPersistError = "persist_write_failed";
            SetBlockedFeedbackByKey(BlockedPersistFailureKey);
            return false;
        }

        _lastPersistError = string.Empty;
        _currentHp = nextHp;
        _deckCards.Clear();
        _deckCards.AddRange(nextDeckCards);
        _selectedOptionId = option.Id;
        HideBlockedFeedback();
        RenderCommittedFeedback(option);

        if (option.HpLoss > 0)
        {
            PublishDarkCostApplied("hp_loss", option.HpLoss);
        }

        if (option.CurseAdd > 0)
        {
            PublishDarkCostApplied("curse_add", option.CurseAdd);
        }

        PublishChoiceCommitted(option.Id);
        return true;
    }

    public int GetCurrentHpForTest()
    {
        return _currentHp;
    }

    public int GetCurseCardCountForTest()
    {
        return _deckCards.Count(cardId => cardId == CurseCardId);
    }

    public string GetSelectedOptionIdForTest()
    {
        return _selectedOptionId;
    }

    public string GetPersistedSelectedOptionIdForTest()
    {
        return _persistedSelectedOptionId;
    }

    public string GetLastPersistErrorForTest()
    {
        return _lastPersistError;
    }

    public void SetPersistFailureForTest(bool enabled)
    {
        _forcePersistFailureForTest = enabled;
    }

    public void ClearRuntimeCacheForTest()
    {
        _persistedSelectedOptionId = string.Empty;
        _persistedHp = 20;
        _persistedDeckCards.Clear();
        _persistedStateInitialized = false;
    }

    public global::Godot.Collections.Array<string> GetDeckCardIdsForTest()
    {
        var result = new global::Godot.Collections.Array<string>();
        foreach (var cardId in _deckCards)
        {
            result.Add(cardId);
        }

        return result;
    }

    public string GetEventTitleForTest()
    {
        return ResolveText(TitleKey);
    }

    public string GetEventDescriptionForTest()
    {
        return ResolveText(DescriptionKey);
    }

    public string GetLoseHpPreviewTextForTest()
    {
        return _loseHpPreviewLabel.Text ?? string.Empty;
    }

    public string GetTakeCursePreviewTextForTest()
    {
        return _takeCursePreviewLabel.Text ?? string.Empty;
    }

    public bool IsChosenOptionVisibleForTest()
    {
        return _chosenOptionLabel.Visible;
    }

    public bool IsResultSummaryVisibleForTest()
    {
        return _resultSummaryLabel.Visible;
    }

    public bool IsNumericChangesVisibleForTest()
    {
        return _numericChangesLabel.Visible;
    }

    public bool IsBlockedFeedbackVisibleForTest()
    {
        return _blockedFeedbackLabel.Visible;
    }

    public string GetChosenOptionTextForTest()
    {
        return _chosenOptionLabel.Text ?? string.Empty;
    }

    public string GetResultSummaryTextForTest()
    {
        return _resultSummaryLabel.Text ?? string.Empty;
    }

    public string GetNumericChangesTextForTest()
    {
        return _numericChangesLabel.Text ?? string.Empty;
    }

    public string GetBlockedFeedbackTextForTest()
    {
        return _blockedFeedbackLabel.Text ?? string.Empty;
    }

    public void SetLocaleForTest(string locale)
    {
        if (string.IsNullOrWhiteSpace(locale))
        {
            return;
        }

        TranslationServer.SetLocale(locale);
        RefreshLocalizationForTest();
    }

    public void RefreshLocalizationForTest()
    {
        EnsureLockedOptions();

        _titleLabel.Text = ResolveText(TitleKey);
        _descriptionLabel.Text = ResolveText(DescriptionKey);
        _loseHpButton.Text = ResolveText(_lockedOptions[0].TextKey);
        _takeCurseButton.Text = ResolveText(_lockedOptions[1].TextKey);
        _loseHpPreviewLabel.Text = ResolveText(PreviewHpLossKey);
        _takeCursePreviewLabel.Text = ResolveText(PreviewCurseKey);
    }

    public global::Godot.Collections.Array<global::Godot.Collections.Dictionary> GetOptionViewsForTest()
    {
        EnsureLockedOptions();
        var result = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();

        foreach (var option in _lockedOptions)
        {
            var costs = new global::Godot.Collections.Array<global::Godot.Collections.Dictionary>();
            if (option.HpLoss > 0)
            {
                costs.Add(new global::Godot.Collections.Dictionary
                {
                    { "type", "hp_loss" },
                    { "value", option.HpLoss },
                });
            }

            if (option.CurseAdd > 0)
            {
                costs.Add(new global::Godot.Collections.Dictionary
                {
                    { "type", "curse_add" },
                    { "value", option.CurseAdd },
                });
            }

            result.Add(new global::Godot.Collections.Dictionary
            {
                { "id", option.Id },
                { "text_key", option.TextKey },
                { "text", ResolveText(option.TextKey) },
                { "dark_costs", costs },
            });
        }

        return result;
    }

    private static string ResolveText(string key)
    {
        var localized = TranslationServer.Translate(key);
        return string.Equals(localized, key, StringComparison.Ordinal) ? key : localized;
    }

    private void RenderCommittedFeedback(EventOption option)
    {
        _chosenOptionLabel.Text = string.Format(
            ResolveText(ChosenOptionLabelKey),
            ResolveText(option.TextKey));
        _chosenOptionLabel.Visible = true;

        _resultSummaryLabel.Text = option.Id switch
        {
            "lose_hp" => ResolveText(ResultSummaryLoseHpKey),
            "take_curse" => ResolveText(ResultSummaryTakeCurseKey),
            _ => ResolveText(ResultSummaryDefaultKey),
        };
        _resultSummaryLabel.Visible = true;

        var numericChanges = option.Id switch
        {
            "lose_hp" => ResolveText(NumericChangesHpLossKey),
            "take_curse" => ResolveText(NumericChangesTakeCurseKey),
            _ => ResolveText(NumericChangesDefaultKey),
        };
        _numericChangesLabel.Text = numericChanges;
        _numericChangesLabel.Visible = true;
    }

    private void HideCommittedFeedback()
    {
        _chosenOptionLabel.Text = string.Empty;
        _chosenOptionLabel.Visible = false;
        _resultSummaryLabel.Text = string.Empty;
        _resultSummaryLabel.Visible = false;
        _numericChangesLabel.Text = string.Empty;
        _numericChangesLabel.Visible = false;
    }

    private void SetBlockedFeedback(string message)
    {
        _blockedFeedbackLabel.Text = message;
        _blockedFeedbackLabel.Visible = true;
    }

    private void SetBlockedFeedbackByKey(string key)
    {
        SetBlockedFeedback(ResolveText(key));
    }

    private void HideBlockedFeedback()
    {
        _blockedFeedbackLabel.Text = string.Empty;
        _blockedFeedbackLabel.Visible = false;
    }

    private EventBusAdapter? ResolveEventBus()
    {
        if (_eventBus is not null && GodotObject.IsInstanceValid(_eventBus))
        {
            return _eventBus;
        }

        _eventBus = GetNodeOrNull<EventBusAdapter>("/root/EventBus");
        return _eventBus;
    }

    private void EnsureLockedOptions()
    {
        if (_lockedOptions.Count > 0)
        {
            return;
        }

        _lockedOptions.Add(new EventOption("lose_hp", "event.option.lose_hp", hpLoss: 3, curseAdd: 0));
        _lockedOptions.Add(new EventOption("take_curse", "event.option.take_curse", hpLoss: 0, curseAdd: 1));
    }

    private bool PersistRuntimeState()
    {
        return PersistRuntimeState(_currentHp, _selectedOptionId, _deckCards);
    }

    private bool PersistRuntimeState(int currentHp, string selectedOptionId, IReadOnlyList<string> deckCardIds)
    {
        if (!WritePersistedStateToDisk(currentHp, selectedOptionId, deckCardIds))
        {
            return false;
        }

        _persistedHp = currentHp;
        _persistedSelectedOptionId = selectedOptionId;
        _persistedDeckCards.Clear();
        _persistedDeckCards.AddRange(deckCardIds);
        _persistedStateInitialized = true;
        return true;
    }

    private void LoadPersistedState()
    {
        if (TryLoadPersistedStateFromDisk())
        {
            HideCommittedFeedback();
            HideBlockedFeedback();
            return;
        }

        if (!_persistedStateInitialized)
        {
            PersistRuntimeState();
            HideCommittedFeedback();
            HideBlockedFeedback();
            return;
        }

        _currentHp = _persistedHp;
        _selectedOptionId = _persistedSelectedOptionId;
        _deckCards.Clear();
        _deckCards.AddRange(_persistedDeckCards);
        HideCommittedFeedback();
        HideBlockedFeedback();
    }

    private static string ResolvePersistedStatePath()
    {
        return ProjectSettings.GlobalizePath($"user://{PersistedStateFileName}");
    }

    private bool WritePersistedStateToDisk(int currentHp, string selectedOptionId, IReadOnlyList<string> deckCardIds)
    {
        if (_forcePersistFailureForTest)
        {
            GD.PushWarning("EventScene forced persistence failure for tests.");
            return false;
        }

        try
        {
            var state = new PersistedEventState
            {
                SelectedOptionId = selectedOptionId,
                CurrentHp = currentHp,
                DeckCardIds = deckCardIds.ToList(),
            };
            File.WriteAllText(ResolvePersistedStatePath(), JsonSerializer.Serialize(state));
            return true;
        }
        catch (Exception ex)
        {
            GD.PushWarning($"EventScene failed to persist task22 state: {ex.Message}");
            return false;
        }
    }

    private bool TryLoadPersistedStateFromDisk()
    {
        try
        {
            var path = ResolvePersistedStatePath();
            if (!File.Exists(path))
            {
                return false;
            }

            var raw = File.ReadAllText(path);
            if (string.IsNullOrWhiteSpace(raw))
            {
                return false;
            }

            var state = JsonSerializer.Deserialize<PersistedEventState>(raw);
            if (state is null)
            {
                return false;
            }

            _selectedOptionId = state.SelectedOptionId ?? string.Empty;
            _currentHp = Math.Max(0, state.CurrentHp);
            _deckCards.Clear();
            foreach (var cardId in state.DeckCardIds ?? new List<string>())
            {
                if (!string.IsNullOrWhiteSpace(cardId))
                {
                    _deckCards.Add(cardId);
                }
            }

            _persistedSelectedOptionId = _selectedOptionId;
            _persistedHp = _currentHp;
            _persistedDeckCards.Clear();
            _persistedDeckCards.AddRange(_deckCards);
            _persistedStateInitialized = true;
            return true;
        }
        catch (Exception ex)
        {
            GD.PushWarning($"EventScene failed to load persisted task22 state: {ex.Message}");
            return false;
        }
    }

    private void PublishEventEntered()
    {
        var bus = ResolveEventBus();
        if (bus is null)
        {
            return;
        }

        var optionIds = _lockedOptions.Select(item => item.Id).ToArray();
        var payload = JsonSerializer.Serialize(new
        {
            run_id = "run.test",
            event_id = EventId,
            node_id = NodeId,
            option_ids = optionIds,
        });

        bus.PublishSimple(EventTypes.EventEntered, "ui.event.scene", payload);
    }

    private void PublishChoiceCommitted(string optionId)
    {
        var bus = ResolveEventBus();
        if (bus is null)
        {
            return;
        }

        var payload = JsonSerializer.Serialize(new
        {
            run_id = "run.test",
            event_id = EventId,
            option_id = optionId,
            result_id = optionId,
        });

        bus.PublishSimple(EventTypes.EventChoiceCommitted, "ui.event.scene", payload);
    }

    private void PublishDarkCostApplied(string costType, int amount)
    {
        var bus = ResolveEventBus();
        if (bus is null)
        {
            return;
        }

        var payload = JsonSerializer.Serialize(new
        {
            run_id = "run.test",
            source_id = EventId,
            cost_type = costType,
            amount,
        });

        bus.PublishSimple(EventTypes.DarkCostApplied, "ui.event.scene", payload);
    }
}
