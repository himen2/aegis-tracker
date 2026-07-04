use pyo3::prelude::*;
use crossbeam_channel::{unbounded, Sender, Receiver};
use serde_json::{Value, json};
use std::thread;
use std::time::Duration;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

#[pyclass]
pub struct RustSender {
    tx: Option<Sender<String>>,
    is_connected: Arc<AtomicBool>,
    base_url: String,
    run_id: String,
    api_token: String,
}

#[pymethods]
impl RustSender {
    #[new]
    #[pyo3(signature = (base_url, run_id, api_token="".to_string()))]
    fn new(base_url: String, run_id: String, api_token: String) -> Self {
        RustSender {
            tx: None,
            is_connected: Arc::new(AtomicBool::new(false)),
            base_url: base_url.trim_end_matches('/').to_string(),
            run_id,
            api_token,
        }
    }

    fn start(&mut self) {
        if self.tx.is_some() {
            return;
        }

        let (tx, rx): (Sender<String>, Receiver<String>) = unbounded();
        self.tx = Some(tx);

        let base_url = self.base_url.clone();
        let run_id = self.run_id.clone();
        let api_token = self.api_token.clone();
        let is_connected = self.is_connected.clone();

        thread::spawn(move || {
            let mut pending = Vec::new();
            let batch_size = 50;
            let timeout = Duration::from_secs(1);
            let url = format!("{}/api/aegis/run/{}/log_batch", base_url, run_id);

            loop {
                // Wait for a message or timeout
                match rx.recv_timeout(timeout) {
                    Ok(msg) => {
                        if msg == "STOP" {
                            // Flush remaining and exit
                            if !pending.is_empty() {
                                let _ = send_batch(&url, &api_token, &pending, &is_connected);
                            }
                            break;
                        }
                        
                        if let Ok(value) = serde_json::from_str::<Value>(&msg) {
                            pending.push(value);
                        }

                        if pending.len() >= batch_size {
                            if send_batch(&url, &api_token, &pending, &is_connected) {
                                pending.clear();
                            } else {
                                // Simple retry delay
                                thread::sleep(Duration::from_secs(2));
                            }
                        }
                    }
                    Err(crossbeam_channel::RecvTimeoutError::Timeout) => {
                        // Timeout reached, flush if we have anything
                        if !pending.is_empty() {
                            if send_batch(&url, &api_token, &pending, &is_connected) {
                                pending.clear();
                            } else {
                                thread::sleep(Duration::from_secs(2));
                            }
                        }
                    }
                    Err(crossbeam_channel::RecvTimeoutError::Disconnected) => {
                        // Channel closed, flush and exit
                        if !pending.is_empty() {
                            let _ = send_batch(&url, &api_token, &pending, &is_connected);
                        }
                        break;
                    }
                }
            }
        });
    }

    fn stop(&mut self) {
        if let Some(tx) = &self.tx {
            let _ = tx.send("STOP".to_string());
        }
    }

    fn enqueue(&self, item_json: String) {
        if let Some(tx) = &self.tx {
            let _ = tx.send(item_json);
        }
    }

    #[getter]
    fn is_connected(&self) -> bool {
        self.is_connected.load(Ordering::Relaxed)
    }
}

fn send_batch(url: &str, api_token: &str, pending: &[Value], is_connected: &Arc<AtomicBool>) -> bool {
    let payload = json!({ "batch": pending });
    
    let mut req = ureq::post(url)
        .set("Content-Type", "application/json")
        .set("X-Aegis-Client", "rust-sdk");
        
    if !api_token.is_empty() {
        req = req.set("X-API-Key", api_token);
    }

    match req.send_json(payload) {
        Ok(_) => {
            is_connected.store(true, Ordering::Relaxed);
            true
        }
        Err(_) => {
            is_connected.store(false, Ordering::Relaxed);
            false
        }
    }
}
