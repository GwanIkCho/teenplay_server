# Generated by Django 5.0.2 on 2024-05-21 09:16

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("member", "0009_alter_member_member_recommended_activity_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="member_recommended_club_model",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="member",
            name="member_recommended_teenplay_model",
            field=models.TextField(null=True),
        ),
    ]