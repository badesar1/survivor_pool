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
        fields = ['safe_pick', 'voted_out_pick', 'imty_challenge_winner_pick', 'used_immunity_idol']
        widgets = {
            'safe_pick': forms.HiddenInput(),
            'voted_out_pick': forms.HiddenInput(),
            'imty_challenge_winner_pick': forms.HiddenInput(),
            'used_immunity_idol': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        # Pop the 'has_immunity_idol' flag; default to False if not provided
        has_immunity_idol = kwargs.pop('has_immunity_idol', False)
        
        available_safe = kwargs.pop('available_safe', Contestant.objects.none())
        available_voted = kwargs.pop('available_voted', Contestant.objects.none())
        super().__init__(*args, **kwargs)
        self.fields['safe_pick'].queryset = available_safe
        self.fields['voted_out_pick'].queryset = available_voted
        self.fields['imty_challenge_winner_pick'].queryset = available_voted

        if not has_immunity_idol:
            # Remove the 'used_immunity_idol' field if the user has no immunity idols
            self.fields.pop('used_immunity_idol')

    def clean(self):
        cleaned_data = super().clean()
        safe_pick = cleaned_data.get('safe_pick')
        voted_out_pick = cleaned_data.get('voted_out_pick')
        imty_challenge_winner_pick = cleaned_data.get('imty_challenge_winner_pick')

        if safe_pick and voted_out_pick and safe_pick == voted_out_pick:
            raise forms.ValidationError("You cannot select the same contestant for both Safe Pick and Voted Out Pick.")

        return cleaned_data