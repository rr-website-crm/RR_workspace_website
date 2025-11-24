# writer/admin.py
from django.contrib import admin
from .models import WriterProject, ProjectIssue, ProjectComment, WriterStatistics


@admin.register(WriterProject)
class WriterProjectAdmin(admin.ModelAdmin):
    list_display = ['job_id', 'writer', 'topic_short', 'word_count', 'deadline', 'status', 'created_at']
    list_filter = ['status', 'referencing', 'created_at']
    search_fields = ['job_id', 'topic', 'writer__email', 'writer__first_name', 'writer__last_name']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Job Information', {
            'fields': ('job_id', 'topic', 'description', 'word_count', 'deadline', 'referencing')
        }),
        ('Assignment', {
            'fields': ('writer', 'allocated_by', 'status')
        }),
        ('Additional Details', {
            'fields': ('special_instructions', 'attachments')
        }),
        ('Submission', {
            'fields': ('submission_file', 'submission_notes', 'submitted_at')
        }),
        ('Timestamps', {
            'fields': ('assigned_at', 'started_at', 'completed_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def topic_short(self, obj):
        return obj.topic[:50] + '...' if len(obj.topic) > 50 else obj.topic
    topic_short.short_description = 'Topic'


@admin.register(ProjectIssue)
class ProjectIssueAdmin(admin.ModelAdmin):
    list_display = ['title', 'project', 'issue_type', 'reported_by', 'status', 'created_at']
    list_filter = ['issue_type', 'status', 'created_at']
    search_fields = ['title', 'description', 'project__job_id']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Issue Details', {
            'fields': ('project', 'issue_type', 'title', 'description', 'status')
        }),
        ('Assignment', {
            'fields': ('reported_by', 'assigned_to')
        }),
        ('Resolution', {
            'fields': ('resolution_notes', 'resolved_by', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']


@admin.register(ProjectComment)
class ProjectCommentAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'comment_short', 'created_at']
    list_filter = ['created_at']
    search_fields = ['project__job_id', 'user__email', 'comment']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    
    def comment_short(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
    comment_short.short_description = 'Comment'


@admin.register(WriterStatistics)
class WriterStatisticsAdmin(admin.ModelAdmin):
    list_display = ['writer', 'total_projects', 'completed_projects', 'pending_projects', 
                    'in_progress_projects', 'total_words_written', 'average_rating', 'last_updated']
    list_filter = ['last_updated']
    search_fields = ['writer__email', 'writer__first_name', 'writer__last_name']
    ordering = ['-last_updated']
    
    fieldsets = (
        ('Writer', {
            'fields': ('writer',)
        }),
        ('Project Counts', {
            'fields': ('total_projects', 'completed_projects', 'pending_projects', 
                      'in_progress_projects', 'issues_count', 'hold_count')
        }),
        ('Performance Metrics', {
            'fields': ('total_words_written', 'on_time_delivery', 'late_delivery', 'average_rating')
        }),
        ('Metadata', {
            'fields': ('last_updated',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['last_updated']