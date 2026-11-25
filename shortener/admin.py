from django.contrib import admin
from .models import ClickEvent, KeyRange, Url


class UrlAdmin(admin.ModelAdmin):
    search_fields = ["uuid", "link"]
    list_display = ["uuid", "short_link", "created_at", "expires_at"]

    def short_link(self, model: Url):
        short = model.link[:64]
        if short != model.link:
            return f"{short}..."
        return short


class KeyRangeAdmin(admin.ModelAdmin):
    list_display = ["start", "end", "node_id", "claimed_at"]
    search_fields = ["node_id"]


class ClickEventAdmin(admin.ModelAdmin):
    list_display = ["key", "clicked_at", "referer"]
    search_fields = ["key", "referer"]


admin.site.register(Url, UrlAdmin)
admin.site.register(KeyRange, KeyRangeAdmin)
admin.site.register(ClickEvent, ClickEventAdmin)
