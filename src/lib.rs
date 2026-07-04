use pyo3::prelude::*;
use pyo3::types::PyDict;
use sysinfo::System;

#[pyfunction]
fn get_cpu_percent() -> PyResult<f32> {
    let mut sys = System::new_all();
    sys.refresh_cpu_all();
    // sleep for 100ms to get an accurate CPU reading, like psutil
    std::thread::sleep(std::time::Duration::from_millis(100));
    sys.refresh_cpu_all();
    
    let cpu_usage = sys.global_cpu_usage();
    Ok(cpu_usage)
}

use std::collections::HashMap;

#[pyfunction]
fn get_memory_mb() -> PyResult<HashMap<String, f64>> {
    let mut sys = System::new_all();
    sys.refresh_memory();
    
    let total_bytes = sys.total_memory();
    let used_bytes = sys.used_memory();
    
    let total_mb = (total_bytes as f64) / 1024.0 / 1024.0;
    let used_mb = (used_bytes as f64) / 1024.0 / 1024.0;
    
    let percent = if total_bytes > 0 {
        (used_bytes as f64 / total_bytes as f64) * 100.0
    } else {
        0.0
    };
    
    let mut dict = HashMap::new();
    dict.insert("ram_used_mb".to_string(), (used_mb * 10.0).round() / 10.0);
    dict.insert("ram_total_mb".to_string(), (total_mb * 10.0).round() / 10.0);
    dict.insert("ram_percent".to_string(), (percent * 10.0).round() / 10.0);
    
    Ok(dict)
}

#[pymodule]
fn aegis_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_cpu_percent, m)?)?;
    m.add_function(wrap_pyfunction!(get_memory_mb, m)?)?;
    Ok(())
}
