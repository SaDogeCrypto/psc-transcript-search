'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  AlertCircle,
  Plus,
  RefreshCw,
  Trash2,
  Play,
  Loader2,
  Calendar,
  Clock,
  CheckCircle,
  XCircle,
  Edit2,
  X,
} from 'lucide-react';
import { PageLayout } from '../components/Layout';
import {
  getSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  toggleSchedule,
  runScheduleNow,
  getStates,
  Schedule,
  ScheduleCreateRequest,
  State,
} from '@/lib/admin-api';

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formData, setFormData] = useState<ScheduleCreateRequest>({
    name: '',
    schedule_type: 'interval',
    schedule_value: '1h',
    target: 'pipeline',
    enabled: true,
    config: {},
  });
  const [formStates, setFormStates] = useState<string[]>([]);
  const [formMaxCost, setFormMaxCost] = useState<string>('');
  const [formMaxHearings, setFormMaxHearings] = useState<string>('');

  const loadData = useCallback(async () => {
    try {
      const [schedulesData, statesData] = await Promise.all([
        getSchedules(),
        getStates(),
      ]);
      setSchedules(schedulesData);
      setStates(statesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const resetForm = () => {
    setFormData({
      name: '',
      schedule_type: 'interval',
      schedule_value: '1h',
      target: 'pipeline',
      enabled: true,
      config: {},
    });
    setFormStates([]);
    setFormMaxCost('');
    setFormMaxHearings('');
    setEditingId(null);
    setShowForm(false);
  };

  const handleEdit = (schedule: Schedule) => {
    setEditingId(schedule.id);
    setFormData({
      name: schedule.name,
      schedule_type: schedule.schedule_type,
      schedule_value: schedule.schedule_value,
      target: schedule.target,
      enabled: schedule.enabled,
      config: schedule.config_json,
    });
    setFormStates((schedule.config_json?.states as string[]) || []);
    setFormMaxCost(schedule.config_json?.max_cost?.toString() || '');
    setFormMaxHearings(schedule.config_json?.max_hearings?.toString() || '');
    setShowForm(true);
  };

  const handleSubmit = async () => {
    setActionLoading('submit');
    try {
      const config: Record<string, unknown> = {};
      if (formStates.length > 0) config.states = formStates;
      if (formMaxCost) config.max_cost = parseFloat(formMaxCost);
      if (formMaxHearings) config.max_hearings = parseInt(formMaxHearings);

      const data = { ...formData, config };

      if (editingId) {
        await updateSchedule(editingId, data);
      } else {
        await createSchedule(data);
      }
      resetForm();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save schedule');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`Delete schedule "${name}"?`)) return;
    setActionLoading(`delete-${id}`);
    try {
      await deleteSchedule(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete schedule');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggle = async (id: number) => {
    setActionLoading(`toggle-${id}`);
    try {
      await toggleSchedule(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle schedule');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRunNow = async (id: number) => {
    setActionLoading(`run-${id}`);
    try {
      await runScheduleNow(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run schedule');
    } finally {
      setActionLoading(null);
    }
  };

  const getScheduleTypeLabel = (type: string) => {
    switch (type) {
      case 'interval': return 'Interval';
      case 'daily': return 'Daily';
      case 'cron': return 'Cron';
      default: return type;
    }
  };

  const getTargetLabel = (target: string) => {
    switch (target) {
      case 'pipeline': return 'Pipeline';
      case 'scraper': return 'Scraper';
      case 'all': return 'All';
      default: return target;
    }
  };

  if (loading) {
    return (
      <PageLayout activeTab="schedules">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="schedules">
      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={20} />
          <div><strong>Error:</strong> {error}</div>
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Pipeline Schedules</h2>
          <p style={{ color: 'var(--gray-500)' }}>
            {schedules.length} schedule{schedules.length !== 1 && 's'} configured
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={() => setShowForm(true)} className="btn btn-primary">
            <Plus size={16} /> Add Schedule
          </button>
          <button onClick={loadData} className="btn btn-secondary">
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </div>

      {/* Create/Edit Form */}
      {showForm && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>{editingId ? 'Edit Schedule' : 'Create Schedule'}</h3>
            <button onClick={resetForm} className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem' }}>
              <X size={16} />
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Nightly Full Run"
                style={{ width: '100%', padding: '0.5rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Schedule Type</label>
              <select
                value={formData.schedule_type}
                onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value })}
                style={{ width: '100%', padding: '0.5rem' }}
              >
                <option value="interval">Interval (e.g., 1h, 30m)</option>
                <option value="daily">Daily (e.g., 08:00)</option>
                <option value="cron">Cron Expression</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Schedule Value *</label>
              <input
                type="text"
                value={formData.schedule_value}
                onChange={(e) => setFormData({ ...formData, schedule_value: e.target.value })}
                placeholder={formData.schedule_type === 'interval' ? '1h, 30m, 4h' : formData.schedule_type === 'daily' ? '08:00' : '0 */4 * * *'}
                style={{ width: '100%', padding: '0.5rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Target</label>
              <select
                value={formData.target}
                onChange={(e) => setFormData({ ...formData, target: e.target.value })}
                style={{ width: '100%', padding: '0.5rem' }}
              >
                <option value="pipeline">Pipeline Only</option>
                <option value="scraper">Scraper Only</option>
                <option value="all">Both</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Max Cost ($)</label>
              <input
                type="number"
                value={formMaxCost}
                onChange={(e) => setFormMaxCost(e.target.value)}
                placeholder="No limit"
                style={{ width: '100%', padding: '0.5rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Max Hearings</label>
              <input
                type="number"
                value={formMaxHearings}
                onChange={(e) => setFormMaxHearings(e.target.value)}
                placeholder="No limit"
                style={{ width: '100%', padding: '0.5rem' }}
              />
            </div>

            <div style={{ gridColumn: 'span 3' }}>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Limit to States (optional)</label>
              <select
                multiple
                value={formStates}
                onChange={(e) => setFormStates(Array.from(e.target.selectedOptions, o => o.value))}
                style={{ width: '100%', minHeight: '80px', padding: '0.5rem' }}
              >
                {states.map(s => (
                  <option key={s.code} value={s.code}>{s.name} ({s.code})</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
            <button onClick={resetForm} className="btn btn-secondary">Cancel</button>
            <button
              onClick={handleSubmit}
              className="btn btn-primary"
              disabled={!formData.name || !formData.schedule_value || actionLoading === 'submit'}
            >
              {actionLoading === 'submit' ? (
                <><Loader2 size={16} className="animate-spin" /> Saving...</>
              ) : (
                <>{editingId ? 'Update' : 'Create'} Schedule</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Schedules List */}
      {schedules.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <Calendar size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem' }}>No schedules configured</h3>
          <p style={{ color: 'var(--gray-500)' }}>Create a schedule to automate pipeline runs.</p>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Name</th>
                <th>Schedule</th>
                <th>Target</th>
                <th>Last Run</th>
                <th>Next Run</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {schedules.map((schedule) => (
                <tr key={schedule.id} style={{ opacity: schedule.enabled ? 1 : 0.6 }}>
                  <td>
                    <button
                      onClick={() => handleToggle(schedule.id)}
                      className="btn"
                      style={{ padding: '0.25rem', background: 'none', border: 'none' }}
                      disabled={actionLoading === `toggle-${schedule.id}`}
                      title={schedule.enabled ? 'Disable' : 'Enable'}
                    >
                      {schedule.enabled ? (
                        <CheckCircle size={20} style={{ color: 'var(--success)' }} />
                      ) : (
                        <XCircle size={20} style={{ color: 'var(--gray-400)' }} />
                      )}
                    </button>
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{schedule.name}</div>
                    {Array.isArray(schedule.config_json?.states) && (schedule.config_json.states as string[]).length > 0 && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        States: {(schedule.config_json.states as string[]).join(', ')}
                      </div>
                    )}
                  </td>
                  <td>
                    <div>{schedule.schedule_display || schedule.schedule_value}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                      {getScheduleTypeLabel(schedule.schedule_type)}
                    </div>
                  </td>
                  <td>
                    <span className="badge badge-secondary">
                      {getTargetLabel(schedule.target)}
                    </span>
                  </td>
                  <td>
                    {schedule.last_run_at ? (
                      <div>
                        <div style={{ fontSize: '0.875rem' }}>
                          {new Date(schedule.last_run_at).toLocaleString()}
                        </div>
                        <span
                          className={`badge ${schedule.last_run_status === 'success' ? 'badge-success' : 'badge-danger'}`}
                          style={{ fontSize: '0.75rem' }}
                        >
                          {schedule.last_run_status}
                        </span>
                      </div>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>Never</span>
                    )}
                  </td>
                  <td>
                    {schedule.next_run_at ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                        <Clock size={14} style={{ color: 'var(--gray-500)' }} />
                        {new Date(schedule.next_run_at).toLocaleString()}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>--</span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                      <button
                        onClick={() => handleRunNow(schedule.id)}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        disabled={actionLoading === `run-${schedule.id}` || !schedule.enabled}
                        title="Run Now"
                      >
                        <Play size={14} />
                      </button>
                      <button
                        onClick={() => handleEdit(schedule)}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        title="Edit"
                      >
                        <Edit2 size={14} />
                      </button>
                      <button
                        onClick={() => handleDelete(schedule.id, schedule.name)}
                        className="btn btn-danger"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        disabled={actionLoading === `delete-${schedule.id}`}
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}
