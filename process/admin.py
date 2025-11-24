# process/admin.py
from django.contrib import admin
from .models import Job, ProcessSubmission, JobComment, DecorationTask


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['job_id', 'topic_preview', 'word_count', 'deadline', 'status', 'writer', 'process_member', 'created_at']
    list_filter = ['status', 'referencing', 'created_at']
    search_fields = ['job_id', 'topic', 'writer__email', 'process_member__email']
    readonly_fields = ['created_at', 'updated_at', 'allocated_at', 'cancelled_at', 'writer_uploaded_at']
    
    fieldsets = (
        ('Job Information', {
            'fields': ('job_id', 'topic', 'word_count', 'deadline', 'referencing')
        }),
        ('Assignment', {
            'fields': ('writer', 'process_member', 'allocator', 'status')
        }),
        ('Writer Files', {
            'fields': ('writer_final_file', 'writer_uploaded_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'allocated_at', 'cancelled_at'),
            'classes': ('collapse',)
        }),
    )
    
    def topic_preview(self, obj):
        return obj.topic[:50] + '...' if len(obj.topic) > 50 else obj.topic
    topic_preview.short_description = 'Topic'


@admin.register(ProcessSubmission)
class ProcessSubmissionAdmin(admin.ModelAdmin):
    list_display = ['job', 'process_member', 'stage', 'submitted_at']
    list_filter = ['stage', 'submitted_at']
    search_fields = ['job__job_id', 'process_member__email']
    readonly_fields = ['submitted_at', 'updated_at']
    
    fieldsets = (
        ('Submission Info', {
            'fields': ('job', 'process_member', 'stage')
        }),
        ('Check Stage Files', {
            'fields': ('ai_file', 'plag_file'),
            'classes': ('collapse',)
        }),
        ('Final Stage Files', {
            'fields': ('final_file', 'grammarly_report', 'other_files'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('submitted_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(JobComment)
class JobCommentAdmin(admin.ModelAdmin):
    list_display = ['job', 'user', 'text_preview', 'created_at']
    list_filter = ['created_at']
    search_fields = ['job__job_id', 'user__email', 'text']
    readonly_fields = ['created_at', 'updated_at']
    
    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Comment'


@admin.register(DecorationTask)
class DecorationTaskAdmin(admin.ModelAdmin):
    list_display = ['job', 'process_member', 'assigned_by', 'is_completed', 'assigned_at']
    list_filter = ['is_completed', 'assigned_at']
    search_fields = ['job__job_id', 'process_member__email']
    readonly_fields = ['assigned_at', 'completed_at']
    
    fieldsets = (
        ('Task Information', {
            'fields': ('job', 'process_member', 'assigned_by', 'is_completed')
        }),
        ('Files', {
            'fields': ('final_file', 'ai_file', 'plag_file', 'other_files')
        }),
        ('Timestamps', {
            'fields': ('assigned_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )