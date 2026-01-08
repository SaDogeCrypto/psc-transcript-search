'use client';

import { X } from 'lucide-react';

// This component is deprecated - sources are now managed through scrapers

interface AddSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function AddSourceModal({ isOpen, onClose, onSuccess }: AddSourceModalProps) {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px' }}>
        <div className="modal-header">
          <h3>Add Source</h3>
          <button onClick={onClose} className="modal-close">
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>
            Individual source management has been replaced with the scraper system.
          </p>
          <p style={{ color: 'var(--gray-600)' }}>
            Use the <strong>Scrapers</strong> section to discover and process hearings from registered states.
          </p>
        </div>

        <div className="modal-footer">
          <button onClick={onClose} className="btn btn-primary">
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
