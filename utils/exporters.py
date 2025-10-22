"""
Bulk Export System for National Archives Discovery Clone

Provides comprehensive export capabilities for large datasets in multiple formats
with memory-efficient streaming and advanced filtering options
"""

import logging
import csv
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Iterator, Callable, Set
from dataclasses import dataclass, asdict
from pathlib import Path
import time
from datetime import datetime
import gzip
import zipfile
import tempfile
import os

from api.models import Record
from utils.streaming import StreamingRecordProcessor, StreamingConfig
from utils.pagination import iterate_all_records

logger = logging.getLogger(__name__)


@dataclass
class ExportConfig:
    """Configuration for export operations"""
    format: str = "csv"  # csv, json, jsonl, xml, excel
    output_path: Optional[str] = None
    compression: Optional[str] = None  # gzip, zip
    chunk_size: int = 1000
    memory_limit_mb: int = 500
    include_fields: Optional[List[str]] = None
    exclude_fields: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None
    sort_by: str = "created_at"
    progress_callback: Optional[Callable[[int, int], None]] = None


class BaseExporter:
    """Base class for all exporters"""
    
    def __init__(self, config: ExportConfig):
        self.config = config
        self.exported_count = 0
        self.start_time = None
        
    def export(self, records: Iterator[Record]) -> str:
        """Export records and return output file path"""
        raise NotImplementedError
        
    def _get_output_path(self, extension: str) -> str:
        """Generate output file path"""
        if self.config.output_path:
            return self.config.output_path
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"discovery_export_{timestamp}.{extension}"
        
        output_dir = Path("data/exports")
        output_dir.mkdir(exist_ok=True)
        
        return str(output_dir / filename)
    
    def _filter_fields(self, record_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Apply field filtering"""
        if self.config.include_fields:
            record_dict = {k: v for k, v in record_dict.items() 
                          if k in self.config.include_fields}
        
        if self.config.exclude_fields:
            record_dict = {k: v for k, v in record_dict.items() 
                          if k not in self.config.exclude_fields}
        
        return record_dict
    
    def _progress_update(self, current: int, total: Optional[int] = None):
        """Update progress"""
        self.exported_count = current
        if self.config.progress_callback:
            self.config.progress_callback(current, total)


class CSVExporter(BaseExporter):
    """Export records to CSV format"""
    
    def export(self, records: Iterator[Record]) -> str:
        output_path = self._get_output_path("csv")
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = None
            headers_written = False
            
            for i, record in enumerate(records):
                record_dict = record.to_dict()
                record_dict = self._filter_fields(record_dict)
                
                # Write headers on first record
                if not headers_written:
                    writer = csv.DictWriter(csvfile, fieldnames=record_dict.keys())
                    writer.writeheader()
                    headers_written = True
                
                # Clean up values for CSV
                cleaned_dict = {}
                for key, value in record_dict.items():
                    if isinstance(value, (list, dict)):
                        cleaned_dict[key] = json.dumps(value) if value else ""
                    elif value is None:
                        cleaned_dict[key] = ""
                    else:
                        cleaned_dict[key] = str(value)
                
                writer.writerow(cleaned_dict)
                
                if (i + 1) % 1000 == 0:
                    self._progress_update(i + 1)
        
        logger.info(f"CSV export complete: {output_path}")
        return output_path


class JSONExporter(BaseExporter):
    """Export records to JSON format"""
    
    def export(self, records: Iterator[Record]) -> str:
        output_path = self._get_output_path("json")
        
        records_list = []
        
        for i, record in enumerate(records):
            record_dict = record.to_dict()
            record_dict = self._filter_fields(record_dict)
            records_list.append(record_dict)
            
            if (i + 1) % 1000 == 0:
                self._progress_update(i + 1)
        
        # Write JSON file
        with open(output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump({
                'metadata': {
                    'exported_at': datetime.now().isoformat(),
                    'total_records': len(records_list),
                    'export_config': asdict(self.config)
                },
                'records': records_list
            }, jsonfile, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON export complete: {output_path}")
        return output_path


class JSONLExporter(BaseExporter):
    """Export records to JSON Lines format (streaming)"""
    
    def export(self, records: Iterator[Record]) -> str:
        output_path = self._get_output_path("jsonl")
        
        with open(output_path, 'w', encoding='utf-8') as jsonlfile:
            for i, record in enumerate(records):
                record_dict = record.to_dict()
                record_dict = self._filter_fields(record_dict)
                
                json.dump(record_dict, jsonlfile, ensure_ascii=False)
                jsonlfile.write('\n')
                
                if (i + 1) % 1000 == 0:
                    self._progress_update(i + 1)
        
        logger.info(f"JSONL export complete: {output_path}")
        return output_path


class XMLExporter(BaseExporter):
    """Export records to XML format"""
    
    def export(self, records: Iterator[Record]) -> str:
        output_path = self._get_output_path("xml")
        
        # Create root element
        root = ET.Element("discovery_export")
        
        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        ET.SubElement(metadata, "exported_at").text = datetime.now().isoformat()
        ET.SubElement(metadata, "format").text = "xml"
        
        # Add records
        records_element = ET.SubElement(root, "records")
        
        for i, record in enumerate(records):
            record_dict = record.to_dict()
            record_dict = self._filter_fields(record_dict)
            
            record_element = ET.SubElement(records_element, "record")
            record_element.set("id", record.id)
            
            for key, value in record_dict.items():
                if value is not None:
                    elem = ET.SubElement(record_element, key)
                    if isinstance(value, (list, dict)):
                        elem.text = json.dumps(value)
                    else:
                        elem.text = str(value)
            
            if (i + 1) % 1000 == 0:
                self._progress_update(i + 1)
        
        # Write XML file
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)  # Pretty print
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"XML export complete: {output_path}")
        return output_path


class ExcelExporter(BaseExporter):
    """Export records to Excel format"""
    
    def export(self, records: Iterator[Record]) -> str:
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for Excel export. Install with: pip install pandas openpyxl")
        
        output_path = self._get_output_path("xlsx")
        
        # Collect records into list
        records_list = []
        for i, record in enumerate(records):
            record_dict = record.to_dict()
            record_dict = self._filter_fields(record_dict)
            
            # Clean up complex fields for Excel
            for key, value in record_dict.items():
                if isinstance(value, (list, dict)):
                    record_dict[key] = json.dumps(value) if value else ""
            
            records_list.append(record_dict)
            
            if (i + 1) % 1000 == 0:
                self._progress_update(i + 1)
        
        # Create DataFrame and export
        df = pd.DataFrame(records_list)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Records', index=False)
            
            # Add metadata sheet
            metadata_df = pd.DataFrame([{
                'exported_at': datetime.now().isoformat(),
                'total_records': len(records_list),
                'format': 'excel'
            }])
            metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
        
        logger.info(f"Excel export complete: {output_path}")
        return output_path


class BulkExportManager:
    """
    Manager for bulk export operations with streaming and compression support
    """
    
    def __init__(self):
        self.exporters = {
            'csv': CSVExporter,
            'json': JSONExporter,
            'jsonl': JSONLExporter,
            'xml': XMLExporter,
            'excel': ExcelExporter
        }
        
    def export_records(self, config: ExportConfig) -> str:
        """
        Export records with specified configuration
        
        Args:
            config: Export configuration
            
        Returns:
            Path to exported file
        """
        if config.format not in self.exporters:
            raise ValueError(f"Unsupported format: {config.format}")
        
        # Get records iterator
        records = iterate_all_records(
            filters=config.filters,
            page_size=config.chunk_size
        )
        
        # Create exporter
        exporter_class = self.exporters[config.format]
        exporter = exporter_class(config)
        
        # Export
        start_time = time.time()
        output_path = exporter.export(records)
        export_time = time.time() - start_time
        
        # Apply compression if requested
        if config.compression:
            output_path = self._compress_file(output_path, config.compression)
        
        logger.info(f"Export completed in {export_time:.1f}s: {output_path}")
        return output_path
    
    def _compress_file(self, file_path: str, compression: str) -> str:
        """Compress exported file"""
        if compression == "gzip":
            compressed_path = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    f_out.writelines(f_in)
            os.remove(file_path)
            return compressed_path
        
        elif compression == "zip":
            compressed_path = f"{file_path}.zip"
            with zipfile.ZipFile(compressed_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(file_path, Path(file_path).name)
            os.remove(file_path)
            return compressed_path
        
        else:
            raise ValueError(f"Unsupported compression: {compression}")
    
    def export_filtered_records(self, 
                               query: Optional[str] = None,
                               archive: Optional[str] = None,
                               date_from: Optional[str] = None,
                               date_to: Optional[str] = None,
                               level: Optional[str] = None,
                               format: str = "csv",
                               output_path: Optional[str] = None,
                               compression: Optional[str] = None) -> str:
        """
        Convenience method for filtered exports
        
        Args:
            query: Search query
            archive: Filter by archive
            date_from: Filter by start date
            date_to: Filter by end date
            level: Filter by level
            format: Export format
            output_path: Output file path
            compression: Compression method
            
        Returns:
            Path to exported file
        """
        filters = {}
        
        if archive:
            filters['archive'] = archive
        if date_from:
            filters['date_from_after'] = date_from
        if date_to:
            filters['date_to_before'] = date_to
        if level:
            filters['level'] = level
        if query:
            filters['title_contains'] = query
        
        config = ExportConfig(
            format=format,
            output_path=output_path,
            compression=compression,
            filters=filters if filters else None
        )
        
        return self.export_records(config)
    
    def export_custom_fields(self, 
                           fields: List[str],
                           format: str = "csv",
                           filters: Optional[Dict[str, Any]] = None,
                           output_path: Optional[str] = None) -> str:
        """
        Export only specific fields
        
        Args:
            fields: List of field names to include
            format: Export format
            filters: Optional filters
            output_path: Output file path
            
        Returns:
            Path to exported file
        """
        config = ExportConfig(
            format=format,
            output_path=output_path,
            include_fields=fields,
            filters=filters
        )
        
        return self.export_records(config)
    
    def get_export_templates(self) -> Dict[str, ExportConfig]:
        """Get predefined export templates"""
        return {
            'basic_csv': ExportConfig(
                format='csv',
                include_fields=['id', 'title', 'reference', 'date_from', 'date_to', 'archive'],
                compression='zip'
            ),
            'full_json': ExportConfig(
                format='json',
                compression='gzip'
            ),
            'metadata_only': ExportConfig(
                format='csv',
                include_fields=['id', 'title', 'reference', 'archive', 'collection', 'level', 'created_at'],
                compression='zip'
            ),
            'research_excel': ExportConfig(
                format='excel',
                include_fields=['title', 'reference', 'date_from', 'date_to', 'description', 
                              'archive', 'collection', 'subjects', 'creators', 'places']
            ),
            'streaming_jsonl': ExportConfig(
                format='jsonl',
                chunk_size=500,
                memory_limit_mb=256,
                compression='gzip'
            )
        }
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported export formats"""
        return list(self.exporters.keys())
    
    def estimate_export_size(self, config: ExportConfig) -> Dict[str, Any]:
        """
        Estimate export file size and time
        
        Args:
            config: Export configuration
            
        Returns:
            Size and time estimates
        """
        # Sample a small number of records to estimate
        sample_records = list(iterate_all_records(
            filters=config.filters,
            page_size=10
        ))
        
        if not sample_records:
            return {
                'estimated_records': 0,
                'estimated_size_mb': 0,
                'estimated_time_minutes': 0
            }
        
        # Calculate average record size
        sample_dict = sample_records[0].to_dict()
        if config.include_fields:
            sample_dict = {k: v for k, v in sample_dict.items() if k in config.include_fields}
        
        avg_record_size = len(json.dumps(sample_dict))
        
        # Estimate total records (this is expensive, cache it)
        from storage.database import DatabaseManager
        db = DatabaseManager()
        total_records = db.get_record_count()  # You may need to implement this
        
        # Format-specific size multipliers
        format_multipliers = {
            'csv': 0.8,      # CSV is compact
            'json': 1.2,     # JSON has overhead
            'jsonl': 1.0,    # JSONL is efficient
            'xml': 1.5,      # XML has tag overhead
            'excel': 1.1     # Excel is compressed
        }
        
        multiplier = format_multipliers.get(config.format, 1.0)
        estimated_size_bytes = total_records * avg_record_size * multiplier
        estimated_size_mb = estimated_size_bytes / 1024 / 1024
        
        # Estimate processing time (based on empirical data)
        records_per_second = 1000  # Adjust based on system performance
        estimated_time_seconds = total_records / records_per_second
        estimated_time_minutes = estimated_time_seconds / 60
        
        return {
            'estimated_records': total_records,
            'estimated_size_mb': round(estimated_size_mb, 2),
            'estimated_time_minutes': round(estimated_time_minutes, 2),
            'avg_record_size_bytes': avg_record_size,
            'format_multiplier': multiplier
        }


# Convenience functions

def quick_csv_export(filters: Optional[Dict[str, Any]] = None,
                    output_path: Optional[str] = None) -> str:
    """Quick CSV export with basic fields"""
    manager = BulkExportManager()
    template = manager.get_export_templates()['basic_csv']
    template.filters = filters
    template.output_path = output_path
    return manager.export_records(template)


def quick_json_export(filters: Optional[Dict[str, Any]] = None,
                     output_path: Optional[str] = None) -> str:
    """Quick JSON export with all fields"""
    manager = BulkExportManager()
    template = manager.get_export_templates()['full_json']
    template.filters = filters
    template.output_path = output_path
    return manager.export_records(template)


def export_research_data(archive: Optional[str] = None,
                        date_from: Optional[str] = None,
                        date_to: Optional[str] = None) -> str:
    """Export data optimized for research with Excel format"""
    manager = BulkExportManager()
    
    filters = {}
    if archive:
        filters['archive'] = archive
    if date_from:
        filters['date_from_after'] = date_from
    if date_to:
        filters['date_to_before'] = date_to
    
    return manager.export_filtered_records(
        archive=archive,
        date_from=date_from,
        date_to=date_to,
        format='excel'
    )
