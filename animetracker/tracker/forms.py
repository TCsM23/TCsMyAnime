from django import forms
from django.contrib.auth.forms import UserCreationForm

from tracker.models import WatchlistEntry


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False, help_text="Optional. Needed to reset your password.")

    class Meta(UserCreationForm.Meta):
        fields = ("username", "email")


class WatchlistEntryForm(forms.ModelForm):
    class Meta:
        model = WatchlistEntry
        fields = ("status", "episodes_watched", "rating", "notes")
        widgets = {
            "rating": forms.NumberInput(attrs={"min": 1, "max": 10}),
            "episodes_watched": forms.NumberInput(attrs={"min": 0}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        total = self.instance.anime.episodes if self.instance.anime_id else None
        if total:
            self.fields["episodes_watched"].widget.attrs["max"] = total
            self.fields["episodes_watched"].help_text = f"out of {total}"
