# Generated by Django 5.0.1 on 2024-01-23 16:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0004_alter_aboutmessage_chat_id_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='botuser',
            old_name='real_status',
            new_name='is_admin',
        ),
    ]
