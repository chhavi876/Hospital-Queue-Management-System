from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *

class StaffAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('username',)
    ordering = ('username',)
    filter_horizontal = ()
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Permissions', {'fields': ('role', 'is_active')}),
    )
    
    def save_model(self, request, obj, form, change):
        if 'password' in form.changed_data:
            obj.set_password(form.cleaned_data['password'])
        super().save_model(request, obj, form, change)

admin.site.register(Service)
admin.site.register(Counter)
admin.site.register(Patient)
admin.site.register(Staff, StaffAdmin)
admin.site.register(QueueEntry)
admin.site.register(QueueHistory)