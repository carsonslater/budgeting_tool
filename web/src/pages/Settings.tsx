import React, { useState, useRef } from 'react';
import type { DragEvent } from 'react';
import { format, parseISO } from 'date-fns';
import { UploadCloud, FolderOpen, Database, Trash2, Download } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { useStageImport, useConfirmImport } from '../hooks/useImport';
import { Edit2, Tag } from 'lucide-react';
import { useCategories, usePayers, useSubcategories, useAllCategoryRecords, useUpdateCategory } from '../hooks/useExpenses';
import { useToast } from '../contexts/ToastContext';
import { apiFetch } from '../api/client';
import styles from './Settings.module.css';
import type { CategoryRow, StagedRow } from '../types';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

export const AppSettings: React.FC = () => {
  const { showToast } = useToast();
  
  // Category Renaming State
  const [editingCatId, setEditingCatId] = useState<number | null>(null);
  const [editingCatName, setEditingCatName] = useState('');

  // Editor State
  const [editCategory, setEditCategory] = useState('');
  const [editSubcategory, setEditSubcategory] = useState('');
  const [editPayer, setEditPayer] = useState('');

  // Import State
  const [isDragging, setIsDragging] = useState(false);
  const [stagedRows, setStagedRows] = useState<StagedRow[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const [backingUp, setBackingUp] = useState(false);
  const [lastBackup, setLastBackup] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Queries & Mutations
  const { data: categories } = useCategories();
  const { data: payers } = usePayers();
  const { data: subcategories } = useSubcategories(editCategory);
  const { data: categoryRecords } = useAllCategoryRecords();
  const updateCategoryMutation = useUpdateCategory();
  
  const stageMutation = useStageImport();
  const confirmMutation = useConfirmImport();

  // ── Data Management ──
  const handleBackup = async () => {
    setBackingUp(true);
    try {
      const res = await apiFetch<{message: string, timestamp: string}>('/api/backup', { method: 'POST' });
      setLastBackup(res.timestamp);
      showToast('Database backed up successfully.', 'success');
    } catch (e: any) {
      showToast(e.message || 'Backup failed', 'error');
    } finally {
      setBackingUp(false);
    }
  };

  const handleOpenFolder = async () => {
    try {
      await apiFetch('/api/open-data-folder', { method: 'POST' });
      showToast('Data folder opened.', 'success');
    } catch (e: any) {
      showToast(e.message, 'error');
    }
  };

  // ── Import Workflow ──
  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);
  
  const processFile = (file: File) => {
    stageMutation.mutate(file, {
      onSuccess: (data) => {
        setStagedRows(data);
        showToast(`Staged ${data.length} transactions.`, 'success');
      },
      onError: (err: any) => {
        showToast(err.message || 'Failed to parse CSV', 'error');
      }
    });
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  // ── Staging Actions ──
  const toggleSelect = (index: number | null) => {
    if (index === null) return;
    const next = new Set(selectedIds);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    setSelectedIds(next);
  };

  const toggleSelectAll = (checked: boolean) => {
    if (checked) {
      const ids = stagedRows.map(r => r.original_index).filter((id): id is number => id !== null);
      setSelectedIds(new Set(ids));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleDeleteSelected = () => {
    setStagedRows(prev => prev.filter(r => r.original_index !== null && !selectedIds.has(r.original_index)));
    setSelectedIds(new Set());
    showToast('Removed selected rows from staging.', 'warning');
  };

  const handleApplyEdits = () => {
    setStagedRows(prev => prev.map(r => {
      if (r.original_index !== null && selectedIds.has(r.original_index)) {
        return {
          ...r,
          category: editCategory || r.category,
          subcategory: editSubcategory || r.subcategory,
          payer: editPayer || r.payer,
        };
      }
      return r;
    }));
    setEditCategory('');
    setEditSubcategory('');
    setEditPayer('');
    showToast('Applied changes to selected rows.', 'success');
  };

  const handleImportSelected = () => {
    const rowsToImport = stagedRows.filter(r => r.original_index !== null && selectedIds.has(r.original_index));
    confirmMutation.mutate(rowsToImport, {
      onSuccess: (res) => {
        showToast(`Imported ${res.imported} rows. Skipped ${res.skipped} duplicates.`, 'success');
        setStagedRows(prev => prev.filter(r => r.original_index !== null && !selectedIds.has(r.original_index)));
        setSelectedIds(new Set());
      },
      onError: (err: any) => {
        showToast(err.message || 'Import failed', 'error');
      }
    });
  };

  const handleRenameCategory = (cat: CategoryRow) => {
    if (!editingCatName.trim()) return;
    updateCategoryMutation.mutate(
      { id: cat.id, data: { name: editingCatName.trim() } },
      {
        onSuccess: () => {
          showToast(`Renamed ${cat.kind} to "${editingCatName.trim()}"`, 'success');
          setEditingCatId(null);
          setEditingCatName('');
        },
        onError: (err: any) => {
          showToast(err.message || 'Failed to rename category', 'error');
        },
      }
    );
  };

  const duplicatesCount = stagedRows.filter(r => r.is_duplicate).length;

  return (
    <div className={styles.container}>
      
      {/* SECTION 1: Data Management */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Data Management</h2>
        <Card padding="md">
          <div className={styles.backupRow}>
            <Button onClick={handleBackup} loading={backingUp}>
              <Database size={16} style={{ marginRight: 8 }} />
              Backup Database
            </Button>
            <Button variant="ghost" onClick={handleOpenFolder}>
              <FolderOpen size={16} style={{ marginRight: 8 }} />
              Open Data Folder
            </Button>
            {lastBackup && (
              <span className={styles.backupTime}>Last backup: {lastBackup}</span>
            )}
          </div>
        </Card>
      </div>

      {/* SECTION 2: Category Management (Surrogate Key renames) */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Category Management</h2>
        <Card padding="md">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
              Rename category or subcategory records by ID without breaking historical expense attribution.
            </div>
            {categoryRecords && categoryRecords.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '0.5rem' }}>
                {categoryRecords.map((c) => (
                  <div
                    key={c.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.5rem 0.75rem',
                      background: 'var(--color-surface-raised)',
                      borderRadius: '6px',
                      fontSize: '0.9rem',
                    }}
                  >
                    {editingCatId === c.id ? (
                      <div style={{ display: 'flex', gap: '0.5rem', width: '100%' }}>
                        <input
                          type="text"
                          value={editingCatName}
                          onChange={(e) => setEditingCatName(e.target.value)}
                          style={{
                            flex: 1,
                            background: 'var(--color-bg)',
                            color: 'var(--color-text)',
                            border: '1px solid var(--color-accent)',
                            borderRadius: '4px',
                            padding: '0.25rem 0.5rem',
                            fontSize: '0.85rem',
                          }}
                          autoFocus
                        />
                        <Button size="sm" onClick={() => handleRenameCategory(c)}>
                          Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingCatId(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Tag size={14} color="var(--color-accent)" />
                          <span style={{ fontWeight: 500 }}>{c.name}</span>
                          <Badge variant="muted">{c.kind}</Badge>
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setEditingCatId(c.id);
                            setEditingCatName(c.name);
                          }}
                        >
                          <Edit2 size={14} />
                        </Button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)' }}>
                No category records found.
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* SECTION 3: Import */}
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Import Bank Statement</h2>
        
        {stagedRows.length === 0 ? (
          /* Step 1: Upload */
          <div 
            className={`${styles.dropZone} ${isDragging ? styles.dropZoneActive : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadCloud size={48} color="var(--color-accent)" />
            <div>
              <div className={styles.dropTitle}>
                {stageMutation.isPending ? 'Parsing...' : 'Drag and drop your CSV here'}
              </div>
              <div className={styles.dropSubtitle}>or click to browse files</div>
            </div>
            
            <div className={styles.formatBadges}>
              <Badge variant="muted">BECU Credit Card</Badge>
              <Badge variant="muted">Chase Credit</Badge>
              <Badge variant="muted">Chase Bank</Badge>
              <Badge variant="muted">Generic</Badge>
            </div>
            <input 
              type="file" 
              accept=".csv" 
              style={{ display: 'none' }} 
              ref={fileInputRef}
              onChange={handleFileChange}
            />
          </div>
        ) : (
          /* Step 2: Review */
          <div className={styles.stagingContainer}>
            
            {/* Table Area */}
            <div>
              <div className={styles.stagingToolbar}>
                <div className={styles.toolbarStats}>
                  <b>{stagedRows.length}</b> rows loaded · <b>{duplicatesCount}</b> duplicates detected
                </div>
                <div className={styles.toolbarActions}>
                  <Button variant="ghost" size="sm" onClick={() => {
                    setStagedRows([]);
                    setSelectedIds(new Set());
                  }}>Clear</Button>
                  
                  {selectedIds.size > 0 && (
                    <>
                      <Button variant="danger" size="sm" onClick={handleDeleteSelected}>
                        <Trash2 size={16} style={{ marginRight: 4 }} /> Delete
                      </Button>
                      <Button size="sm" onClick={handleImportSelected} loading={confirmMutation.isPending}>
                        <Download size={16} style={{ marginRight: 4 }} /> Import Selected
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th style={{ width: 40 }}>
                        <input 
                          type="checkbox" 
                          className={styles.checkbox}
                          checked={selectedIds.size === stagedRows.length && stagedRows.length > 0}
                          onChange={(e) => toggleSelectAll(e.target.checked)}
                        />
                      </th>
                      <th>Date</th>
                      <th>Description</th>
                      <th className={styles.amountCell}>Amount</th>
                      <th>Category</th>
                      <th>Subcategory</th>
                      <th>Payer</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stagedRows.map((r, i) => (
                      <tr 
                        key={r.original_index ?? i} 
                        className={`
                          ${selectedIds.has(r.original_index as number) ? styles.selected : ''} 
                          ${r.is_duplicate ? styles.duplicateRow : ''}
                        `}
                        onClick={() => toggleSelect(r.original_index)}
                      >
                        <td onClick={(e) => e.stopPropagation()}>
                          <input 
                            type="checkbox" 
                            className={styles.checkbox}
                            checked={selectedIds.has(r.original_index as number)}
                            onChange={() => toggleSelect(r.original_index)}
                          />
                        </td>
                        <td>{format(parseISO(r.date), 'MMM d')}</td>
                        <td style={{ fontWeight: 500 }}>
                          {r.description}
                          {r.is_duplicate && <span style={{ marginLeft: 8 }}><Badge variant="danger">Duplicate</Badge></span>}
                        </td>
                        <td className={styles.amountCell}>{formatCurrency(r.amount)}</td>
                        <td>{r.category || '-'}</td>
                        <td>{r.subcategory || '-'}</td>
                        <td>{r.payer || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right Sidebar Editor */}
            <Card title={`Edit Selected (${selectedIds.size})`} padding="md">
              <div className={styles.editorForm}>
                <Input
                  label="Category"
                  list="cat-list"
                  value={editCategory}
                  onChange={e => setEditCategory(e.target.value)}
                  disabled={selectedIds.size === 0}
                />
                <Input
                  label="Subcategory"
                  list="subcat-list"
                  value={editSubcategory}
                  onChange={e => setEditSubcategory(e.target.value)}
                  disabled={selectedIds.size === 0}
                />
                <Input
                  label="Payer"
                  list="payer-list"
                  value={editPayer}
                  onChange={e => setEditPayer(e.target.value)}
                  disabled={selectedIds.size === 0}
                />
                <Button 
                  disabled={selectedIds.size === 0} 
                  onClick={handleApplyEdits}
                >
                  Apply Changes
                </Button>
              </div>

              <datalist id="cat-list">
                {categories?.map(c => <option key={c} value={c} />)}
              </datalist>
              <datalist id="subcat-list">
                {subcategories?.map(s => <option key={s} value={s} />)}
              </datalist>
              <datalist id="payer-list">
                {payers?.map(p => <option key={p} value={p} />)}
              </datalist>
            </Card>

          </div>
        )}
      </div>
      
    </div>
  );
};

export default AppSettings;
