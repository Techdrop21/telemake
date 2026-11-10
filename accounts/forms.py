from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError


class BusinessRegistrationForm(UserCreationForm):
    """
    Registration form for new business owners.
    Creates both a User account and BusinessOwner profile.
    """
    business_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            "placeholder": "Your Business Name",
            "class": "form-control",
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "business@example.com",
            "class": "form-control",
        }),
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "+263 712 345 678",
            "class": "form-control",
        }),
    )

    class Meta:
        model = User
        fields = ["business_name", "email", "phone", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({
            "placeholder": "Password",
            "class": "form-control",
        })
        self.fields["password2"].widget.attrs.update({
            "placeholder": "Confirm Password",
            "class": "form-control",
        })

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise ValidationError("A business with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]  # Use email as username
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class BusinessLoginForm(forms.Form):
    """Simple login form using email and password."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "business@example.com",
            "class": "form-control",
            "autocomplete": "email",
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            "placeholder": "Password",
            "class": "form-control",
            "autocomplete": "current-password",
        }),
    )
