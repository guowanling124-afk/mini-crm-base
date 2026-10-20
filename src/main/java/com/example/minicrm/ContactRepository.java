package com.example.minicrm;

import org.springframework.stereotype.Repository;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * In-memory contact store. No database on purpose — the app is a stage, not the
 * thing under test. State resets on every restart, which is fine for a testbed.
 */
@Repository
public class ContactRepository {

    private final ConcurrentHashMap<Long, Contact> store = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(0);

    public ContactRepository() {
        // Seed a couple of rows so the UI is not empty on first load.
        save(new Contact(null, "Ada Lovelace", "ada@example.com", "Analytical Engines"));
        save(new Contact(null, "Alan Turing", "alan@example.com", "Bletchley Park"));
    }

    public List<Contact> findAll() {
        return new ArrayList<>(store.values());
    }

    public Optional<Contact> findById(Long id) {
        return Optional.ofNullable(store.get(id));
    }

    public Contact save(Contact contact) {
        if (contact.getId() == null) {
            contact.setId(sequence.incrementAndGet());
        }
        store.put(contact.getId(), contact);
        return contact;
    }

    public boolean deleteById(Long id) {
        return store.remove(id) != null;
    }
}
