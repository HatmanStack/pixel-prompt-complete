/**
 * Expand Component
 * Collapsible section with smooth animation
 */

import { useState, useRef, useEffect, useId } from 'react';
import PropTypes from 'prop-types';
import { useApp } from '../../context/AppContext';
import styles from './Expand.module.css';

function Expand({ title, children, defaultExpanded = false, onToggle }) {
  const uniqueId = useId();
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [height, setHeight] = useState(defaultExpanded ? 'auto' : '0px');
  const contentRef = useRef(null);
  const collapseTimerRef = useRef(null);
  const { playSound } = useApp();

  // Update height when expanded state changes
  useEffect(() => {
    if (contentRef.current) {
      if (isExpanded) {
        // Set to scrollHeight when expanding
        const scrollHeight = contentRef.current.scrollHeight;
        setHeight(`${scrollHeight}px`);

        // After animation, set to auto for dynamic content
        const timer = setTimeout(() => {
          setHeight('auto');
        }, 300); // Match CSS transition duration

        return () => clearTimeout(timer);
      } else {
        // Set to scrollHeight first, then to 0 for smooth collapse
        const scrollHeight = contentRef.current.scrollHeight;
        setHeight(`${scrollHeight}px`);

        // Force reflow
        collapseTimerRef.current = setTimeout(() => {
          setHeight('0px');
        }, 10);

        return () => {
          if (collapseTimerRef.current) {
            clearTimeout(collapseTimerRef.current);
          }
        };
      }
    }
  }, [isExpanded]);

  const handleToggle = () => {
    const newState = !isExpanded;
    setIsExpanded(newState);

    // Play sound effect
    playSound('expand');

    // Call onToggle callback if provided
    if (onToggle) {
      onToggle(newState);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleToggle();
    }
  };

  return (
    <div className={styles.expand}>
      <button
        className={styles.header}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        aria-expanded={isExpanded}
        aria-controls={uniqueId}
        type="button"
      >
        <span className={styles.title}>{title}</span>
        <span
          className={`${styles.icon} ${isExpanded ? styles.iconExpanded : ''}`}
          aria-hidden="true"
        >
          ▼
        </span>
      </button>

      <div
        ref={contentRef}
        id={uniqueId}
        className={styles.content}
        style={{ height }}
        aria-hidden={!isExpanded}
      >
        <div className={styles.contentInner}>{children}</div>
      </div>
    </div>
  );
}

Expand.propTypes = {
  title: PropTypes.string.isRequired,
  children: PropTypes.node.isRequired,
  defaultExpanded: PropTypes.bool,
  onToggle: PropTypes.func,
};

Expand.defaultProps = {
  defaultExpanded: false,
  onToggle: null,
};

export default Expand;
