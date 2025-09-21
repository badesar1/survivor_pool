# poolapp/forms.py

from django import forms
from .models import Pick, Contestant
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class ExtendedUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        help_text="Enter a valid email address for reminders and updates.",
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email address',
            'class': 'form-control'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def save(self, commit=True):
        # Save the provided email in the User model
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user

class ResetPicksForm(forms.Form):
    pass

class PickForm(forms.ModelForm):
    class Meta:
        model = Pick
        fields = [
            'safe_pick', 'voted_out_pick', 'imty_challenge_winner_pick', 'used_immunity_idol',
            'wager_voted_out', 'wager_immunity', 'parlay'
        ]
        widgets = {
            'safe_pick': forms.HiddenInput(),
            'voted_out_pick': forms.HiddenInput(),
            'imty_challenge_winner_pick': forms.HiddenInput(),
            'used_immunity_idol': forms.HiddenInput(),
            # You can switch to visible NumberInput if you prefer showing sliders/inputs:
            'wager_voted_out': forms.HiddenInput(),
            'wager_immunity': forms.HiddenInput(),
            'parlay': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        self.has_immunity_idol = kwargs.pop('has_immunity_idol', False)
        self.available_safe = kwargs.pop('available_safe', None)
        self.available_voted = kwargs.pop('available_voted', None)
        # NEW: supply current_points and weekly_cap for validation
        self.current_points = kwargs.pop('current_points', 0)
        self.weekly_cap = kwargs.pop('weekly_cap', 3)
        self.min_floor = kwargs.pop('min_floor', -3)

        super().__init__(*args, **kwargs)
        self.fields['safe_pick'].required = False
        self.fields['voted_out_pick'].required = False
        self.fields['imty_challenge_winner_pick'].required = False

        if not self.has_immunity_idol:
            self.fields.pop('used_immunity_idol', None)

        # Default wagers to 0 if missing from POST
        if 'wager_voted_out' in self.fields:
            self.fields['wager_voted_out'].required = False
        if 'wager_immunity' in self.fields:
            self.fields['wager_immunity'].required = False
        if 'parlay' in self.fields:
            self.fields['parlay'].required = False

    def clean(self):
        cleaned = super().clean()
        used_idol = cleaned.get('used_immunity_idol')
        s, v = cleaned.get('safe_pick'), cleaned.get('voted_out_pick')

        # Your existing constraint when idol not used
        if not used_idol and s and v and s == v:
            raise forms.ValidationError("You cannot select the same contestant for both Safe Pick and Voted Out Pick.")

        # --- Wager validation ---
        wager_vo = cleaned.get('wager_voted_out') or 0
        wager_im = cleaned.get('wager_immunity') or 0
        if wager_vo < 0 or wager_im < 0:
            raise forms.ValidationError("Wagers must be non-negative.")
        if (wager_vo + wager_im) > self.weekly_cap:
            raise forms.ValidationError(f"Total wager exceeds weekly cap of {self.weekly_cap} points.")

        # --- Floor check (cannot drop below -3 on submission) ---
        # We only deduct wagers if picks are wrong; but players are 'risking' spend.
        # To keep it simple and safe for UX, ensure user has at least enough room to risk:
        projected_floor = self.current_points - (wager_vo + wager_im)
        if projected_floor < self.min_floor:
            raise forms.ValidationError(f"Insufficient balance to risk that many points (min balance {self.min_floor}). Reduce wagers.")

        # --- Parlay requires both picks present (VO & Immunity) ---
        parlay = cleaned.get('parlay') or False
        if parlay and (not cleaned.get('voted_out_pick') or not cleaned.get('imty_challenge_winner_pick')):
            raise forms.ValidationError("Parlay requires both a Voted Out pick and an Immunity pick.")

        return cleaned